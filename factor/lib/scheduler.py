"""
Module defining the operation scheduler class
"""
import logging
import multiprocessing
import os
import sys
import imp
import numpy as np
from collections import Counter
from factor.lib.context import Timer

log = logging.getLogger('factor:scheduler')


def call_generic_pipeline(op_name, direction_name, parset, config, logbasename,
    genericpipeline_executable):
    """
    Creates a GenericPipeline object and runs the pipeline

    Parameters
    ----------
    op_name : str
        Name of operation
    direction_name : str
        Name of direction
    parset : str
        Name of pipeline parset file
    config : str
        Name of pipeline config file
    logbasename : str
        Log file base name
    genericpipeline_executable : str
        Path to genericpipeline.py executable

    """
    from lofarpipe.support.pipelinelogging import getSearchingLogger
    from factor.lib.context import RedirectStdStreams
    genericpipeline_path = os.path.dirname(genericpipeline_executable)
    loader = imp.load_source('loader', os.path.join(genericpipeline_path,
        'loader.py'))
    gp = imp.load_source('gp', genericpipeline_executable)

    # Initalize pipeline object
    pipeline = gp.GenericPipeline()

    # Add needed attr/methods
    pipeline.name = '{0}_{1}'.format(op_name, direction_name)
    pipeline.logger = getSearchingLogger(pipeline.name)
    pipeline.inputs['args'] = [parset]
    pipeline.inputs['config'] = config
    pipeline.inputs['job_name'] = direction_name

    # Set pipeline logging to DEBUG level
    logging.root.setLevel(logging.DEBUG)
    pipeline.logger.setLevel(logging.DEBUG)
    for handler in pipeline.logger.handlers:
        handler.setLevel(logging.DEBUG)

    # Run the pipeline, redirecting screen output to log files
    log.info('<-- Operation {0} started (direction: {1})'.format(op_name,
        direction_name))
    with open("{0}.out.log".format(logbasename), "wb") as out, \
        open("{0}.err.log".format(logbasename), "wb") as err:
        with RedirectStdStreams(stdout=out, stderr=err):
            status = pipeline.run(pipeline.name)

    return (op_name, direction_name, status)


class Scheduler(object):
    """
    The scheduler runs all jobs sent to it in parallel

    Parameters
    ----------
    genericpipeline_executable : str
        Path to genericpipeline.py executable
    max_procs : int, optional
        Limit the number of parallel processes to this number
    name : str, optional
        Name of the scheduler
    dry_run : bool, optional
        If True, the pipelines are not run but all parsets and config files
        are made as normal

    """
    def __init__(self, genericpipeline_executable, max_procs=1, name='scheduler',
        dry_run=False):
        self.genericpipeline_executable = genericpipeline_executable
        self.max_procs = max_procs
        self.name = name
        self.dry_run = dry_run
        self.success = True


    def allocate_resources(self, operation_list=None):
        """
        Divide up nodes and cpus among the operations to be run in parallel

        Parameters
        ----------
        operation_list : list of Operation objects, optional
            Input list of operations over which to distribute the resources. If
            None, self.operation_list is used

        The following attributes of the direction object of each operation are
        set:
            max_cpus_per_node : maximum number of cores that the pipeline
                should use
            max_io_proc_per_node : maximum number of IO-intensive processes
            max_cpus_per_chunk : number of threads in NDPPP calls that are run
                "ntimes" times
            max_cpus_per_band : number of threads in NDPPP calls that are run
                "nfiles" times
            max_percent_memory : percentage of memory to give to WSClean

        """
        if operation_list is None:
            operation_list = self.operation_list

        node_list = self.operation_list[0].node_list
        ncpu_max = self.operation_list[0].parset['cluster_specific']['ncpu']
        fmem_max = self.operation_list[0].parset['cluster_specific']['wsclean_fmem']
        nops_per_node = max(self.operation_list[0].parset['cluster_specific']['ndir_per_node'],
            self.operation_list[0].parset['cluster_specific']['nimg_per_node'])
        nbands = len(self.operation_list[0].bands)
        nops_simul = self.max_procs

        for i in range(int(np.ceil(len(operation_list)/float(nops_simul)))):
            op_group = operation_list[i*nops_simul:(i+1)*nops_simul]

            if len(op_group) >= len(node_list):
                for i in range(len(op_group)-len(node_list)):
                    node_list.append(node_list[i])
                hosts = [[n] for n in node_list]
            else:
                parts = len(op_group)
                hosts = [node_list[i*len(node_list)//parts:
                    (i+1)*len(node_list)//parts] for i in range(parts)]

            # Find duplicates and divide up available nodes and cores
            h_flat = []
            for h in hosts:
                h_flat.extend(h)
            c = Counter(h_flat)

            for op, h in zip(op_group, hosts):
                if len(h) == 1:
                    nops_per_node = min(nops_per_node, c[h[0]])
                else:
                    nops_per_node = 1
                nchunks_per_node = max(1, int(round(float(
                    len(op.bands[0].files)) / len(h))))

                op.direction.hosts = h
                op.direction.max_cpus_per_node =  max(1, int(round(ncpu_max /
                    float(nops_per_node))))
                op.direction.max_io_proc_per_node = int(np.ceil(np.sqrt(op.direction.max_cpus_per_node)))
                op.direction.max_cpus_per_chunk = int(round(op.direction.max_cpus_per_node /
                    nchunks_per_node))
                op.direction.max_cpus_per_band = max(1, int(round(op.direction.max_cpus_per_node *
                    len(op.direction.hosts) / float(nbands))))
                op.direction.max_percent_memory = fmem_max / float(nops_per_node) * 100.0
                op.direction.save_state()


    def result_callback(self, result):
        """
        Callback function for apply_async result
        """
        op_name, direction_name, status = result

        # Identify the current operation from the direction name
        try:
            this_op_indx = [op.direction.name for op in self.operation_list].index(direction_name)
            this_op =  self.operation_list[this_op_indx]
        except ValueError:
            log.warn('Operation {0} (direction: {1}) not in list of active '
                'operations. This could indicate a problem with the operation'.
                format(op_name, direction_name))
            return

        # Reallocate resources
        if len(self.queued_ops) > 0:
            # Give the completed op's resources to the next one in line (if any)
            next_op = self.queued_ops.pop(0)
            next_op.direction.hosts = this_op.direction.hosts[:]
            next_op.setup()

        # Finalize the operation
        if status == 0:
            log.info('--> Operation {0} completed (direction: '
                '{1})'.format(op_name, direction_name))
            this_op.finalize()
            this_op.set_completed()
        else:
            log.error('Operation {0} failed due to an error (direction: '
                '{1})'.format(op_name, direction_name))
            self.success = False


    def run(self, operation_list):
        """
        Runs a list of operations in parallel

        Parameters
        ----------
        operation_list : Operation instance or list of Operation instances
            List of operations to process

        """
        if type(operation_list) != list:
            operation_list = [operation_list]

        # Finalize completed ops (so that various attributes are set correctly).
        # The incomplete ops are finalized when complete in self.result_callback()
        if self.dry_run:
            completed_ops = operation_list
        else:
            completed_ops = [op for op in operation_list if op.check_completed()]
        for op in completed_ops:
            op.finalize()

        # Filter out completed ops
        self.operation_list = [op for op in operation_list if not op.check_completed()]
        if len(self.operation_list) == 0 or self.dry_run:
            return

        # Run the operation(s)
        self.allocate_resources()
        with Timer(log, 'operation'):
            pool = multiprocessing.Pool(processes=self.max_procs)
            self.queued_ops = self.operation_list[self.max_procs:]
            for op in self.operation_list:
                op.setup()
                op.set_started()
                pool.apply_async(call_generic_pipeline, (op.name,
                    op.direction.name, op.pipeline_parset_file,
                    op.pipeline_config_file, op.logbasename,
                    self.genericpipeline_executable),
                    callback=self.result_callback)
            pool.close()
            pool.join()

        if not self.success:
            log.error('One or more operations failed due to an error. Exiting...')
            sys.exit(1)
