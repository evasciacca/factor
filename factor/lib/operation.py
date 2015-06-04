"""
General operation library

Contains the master class for operations
"""
import os
import logging
import socket
from factor.lib.context import Timer
from factor.lib.scheduler_mp import Scheduler
from factor import _logging
from jinja2 import Environment, FileSystemLoader
from distutils import spawn
from lofarpipe.support.utilities import create_directory

DIR = os.path.dirname(os.path.abspath(__file__))
env_parset = Environment(loader=FileSystemLoader(os.path.join(DIR, '..', 'pipeline',
    'parsets')))
env_config = Environment(loader=FileSystemLoader(os.path.join(DIR, '..', 'pipeline')))


class Operation(object):
    """
    Generic operation class.
    """
    def __init__(self, parset, bands, direction, name=None):
        """
        Create Operation object

        Parameters
        ----------
        parset : str
            Parset of operation
        bands : list of Band objects
            Bands for this operation
        direction : Direction object
            Direction for this operation
        name : str, optional
            Name of the action
        """
        self.parset = parset.copy()
        self.bands = bands
        self.name = name.lower()
        self.parset['op_name'] = name
        self.direction = direction
        _logging.set_level(self.parset['logging_level'])
        self.log = logging.getLogger('factor.{0}'.format(self.name))
        self.hostname = socket.gethostname()
        self.node_list = parset['cluster_specific']['node_list']

        # Below are paths for output directories
        self.factor_working_dir = parset['dir_working']
        # Name of state file
        self.statebasename = '{0}/state/{1}-{2}'.format(self.factor_working_dir,
            self.name, self.direction.name)
        # Directory that holds important mapfiles in a convenient place
        self.mapfile_dir = '{0}/datamaps/{1}/{2}'.format(self.factor_working_dir,
            self.name, self.direction.name)
        create_directory(self.mapfile_dir)
        # Pipeline runtime dir (pipeline makes subdir here with name of direction)
        self.pipeline_runtime_dir = os.path.join(self.factor_working_dir, 'results',
            self.name)
        create_directory(self.pipeline_runtime_dir)
        # Directory that holds parset and config files
        self.pipeline_parset_dir = os.path.join(self.pipeline_runtime_dir,
            self.direction.name)
        create_directory(self.pipeline_parset_dir)
        # Pipeline working dir (pipeline makes subdir here with name of direction)
        self.pipeline_working_dir = os.path.join(self.factor_working_dir, 'results',
            self.name)
        create_directory(self.pipeline_working_dir)
        # Directory that holds logs in a convenient place
        self.log_dir = '{0}/logs/{1}/{2}/'.format(self.factor_working_dir,
            self.name, self.direction.name)
        create_directory(self.log_dir)
        # Log name used for logs in log_dir
        self.logbasename = os.path.join(self.log_dir, '{0}_{1}'.format(
            self.name, self.direction.name))

        # Below are paths for scripts, etc. in the Factor install directory
        self.factor_root_dir = os.path.split(DIR)[0]
        self.factor_pipeline_dir = os.path.join(self.factor_root_dir, 'pipeline')
        self.factor_script_dir = os.path.join(self.factor_root_dir, 'scripts')
        self.factor_parset_dir = os.path.join(self.factor_root_dir, 'parsets')
        self.factor_skymodel_dir = os.path.join(self.factor_root_dir, 'skymodels')

        # Below are the templates and output paths for the pipeline parset and
        # config files
        self.pipeline_parset_template = env_parset.get_template('{0}_pipeline.parset'.
            format(self.name))
        self.pipeline_parset_file = os.path.join(self.pipeline_parset_dir,
            'pipeline.parset')
        self.pipeline_config_template = env_config.get_template('pipeline.cfg')
        self.pipeline_config_file = os.path.join(self.pipeline_parset_dir,
            'pipeline.cfg')

        # Define parameters needed for the pipeline config. Parameters needed
        # for the pipeline parset should be defined in the subclasses in
        # self.parms_dict
        self.cfg_dict = {'lofarroot': parset['lofarroot'],
                         'pythonpath': parset['lofarpythonpath'],
                         'factorroot': self.factor_root_dir,
                         'genericpiperoot': parset['piperoot'],
                         'pipeline_working_dir': self.pipeline_working_dir,
                         'pipeline_runtime_dir': self.pipeline_runtime_dir,
                         'casa_executable': spawn.find_executable('casa'),
                         'wsclean_executable': spawn.find_executable('wsclean')}


    def setup(self):
        """
        Set up this operation

        This involves just filling the pipeline config and parset templates
        """
        tmp = self.pipeline_parset_template.render(self.parms_dict)
        with open(self.pipeline_parset_file, 'w') as f:
            f.write(tmp)
        tmp = self.pipeline_config_template.render(self.cfg_dict)
        with open(self.pipeline_config_file, 'w') as f:
            f.write(tmp)


    def finalize(self):
        """
        Finalize this operation

        This should be defined in the subclasses if needed
        """
        pass


    def check_completed(self):
        """
        Checks whether operation has been run successfully before

        Returns
        -------
        all_done : bool
            True if all objects were successfully run

        """
        self.direction.load_state()
        if self.name in self.direction.completed_operations:
            all_done = True
        else:
            all_done = False

        return all_done


    def set_completed(self):
        """
        Sets the state for the operation
        """
        self.direction.completed_operations.append(self.name)
        self.direction.save_state()
