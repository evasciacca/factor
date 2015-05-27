"""
Module that holds all solution-related actions

Classes
-------
Losoto : Action
    Runs LoSoTo
Smooth : Action
    Smooths and normalizes solutions
ResetPhases : Action
    Resets phases to zero

"""

from factor.lib.action import Action
from factor.lib.action_lib import make_basename
from jinja2 import Environment, FileSystemLoader
import os

DIR = os.path.dirname(os.path.abspath(__file__))
env = Environment(loader=FileSystemLoader(os.path.join(DIR, 'templates')))


class Losoto(Action):
    """
    Action to run LoSoTo

    Input data maps
    ---------------
    vis_datamap : Datamap
        Map of vis data files
    parmdb_datamap : Datamap
        Map of input parmdb files

    Output data maps
    ----------------
    output_datamap : Datamap
        Map of output parmdb files

    """
    def __init__(self, op_parset, vis_datamap, p, parmdb_datamap, prefix=None,
        direction=None, clean=True, index=None, name='Losoto'):
        """
        Create action and run pipeline

        Parameters
        ----------
        op_parset : dict
            Parset dict of the calling operation
        vis_datamap : data map
            Input data map for vis files
        p : dict
            Input parset dict defining model and pipeline parameters
        parmdb_datamap : data map
            Input data map for parmdb files
        prefix : str, optional
            Prefix to use for model names
        direction : Direction object, optional
            Direction for this model
        clean : bool, optional
            Remove unneeded files?
        index : int, optional
            Index of action

        """
        super(Losoto, self).__init__(op_parset, name=name, prefix=prefix,
            direction=direction, index=index)

        # Store input parameters
        self.vis_datamap = vis_datamap
        self.parmdb_datamap = parmdb_datamap
        self.p = p.copy()
        if prefix is None:
            prefix = 'run_losoto'
        self.clean = clean
        self.working_dir = self.parmdb_dir + '{0}/{1}/'.format(self.op_name, self.name)
        if self.direction is not None:
            self.working_dir += '{0}/'.format(self.direction.name)
        if not os.path.exists(self.working_dir):
            os.makedirs(self.working_dir)

        # Define parset name
        self.parset_file = self.parsetbasename + '.parset'
        self.templatename = '{0}_{1}.parset.tpl'.format(prefix, self.name.lower())

        # Set up all required files
        self.setup()


    def make_datamaps(self):
        """
        Makes the required data maps
        """
        from factor.lib.datamap_lib import read_mapfile

        self.p['input_datamap'] = self.vis_datamap

        parmdb_names, hosts = read_mapfile(self.parmdb_datamap)
        h5parm_files = [parmdb_name + '.h5parm' for parmdb_name in parmdb_names]
        self.p['h5parm_datamap'] = self.write_mapfile(h5parm_files,
            prefix=self.prefix+'_h5parm', direction=self.direction,
            index=self.index, host_list=hosts)


    def make_pipeline_control_parset(self):
        """
        Writes the pipeline control parset and any script files
        """
        from distutils import spawn

        if 'ncpu' not in self.p:
            self.p['ncpu'] = self.max_cpu
        if 'n_per_node' not in self.p:
            self.p['n_per_node'] = self.max_cpu
        self.p['lofarroot'] = self.op_parset['lofarroot']
        self.p['parset'] = self.parset_file

        # Get full paths to executables
        self.p['losoto_exec'] = spawn.find_executable("losoto.py")
        self.p['h5importer_exec'] = spawn.find_executable("H5parm_importer.py")
        self.p['h5exporter_exec'] = spawn.find_executable("H5parm_exporter.py")

        template = env.get_template('losoto.pipeline.parset.tpl')
        tmp = template.render(self.p)
        with open(self.pipeline_parset_file, 'w') as f:
            f.write(tmp)

        template = env.get_template('losoto_finalize.tpl')
        tmp = template.render(self.p)
        with open(self.pipeline_parset_file, 'w') as f:
            f.write(tmp)

        template = env.get_template('losoto_prepare.tpl')
        tmp = template.render(self.p)
        with open(self.pipeline_parset_file, 'w') as f:
            f.write(tmp)

        template = env.get_template(self.templatename)
        tmp = template.render(self.p)
        with open(self.parset_file, 'w') as f:
            f.write(tmp)


    def get_results(self):
        """
        Return results
        """
        return self.parmdb_datamap


class Smooth(Losoto):
    """
    Action to smooth and normalize solutions
    """
    def __init__(self, op_parset, vis_datamap, p, parmdb_datamap, prefix=None,
        direction=None, clean=True, index=None):
        super(Smooth, self).__init__(op_parset, vis_datamap, p, parmdb_datamap,
            prefix=prefix, direction=direction, clean=clean, index=index,
            name='Smooth')


class ResetPhases(Losoto):
    """
    Action to reset phases to zero
    """
    def __init__(self, op_parset, vis_datamap, p, parmdb_datamap, prefix=None,
        direction=None, clean=True, index=None):
        super(ResetPhases, self).__init__(op_parset, vis_datamap, p, parmdb_datamap,
            prefix=prefix, direction=direction, clean=clean, index=index,
            name='ResetPhases')
