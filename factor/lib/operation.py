"""
General operation library, contains the master class for operations
Operations have the parallelized part of the code.
"""
import logging
from factor.lib.scheduler import scheduler

class operation( object ):
    """
    General class for operations. All operations should be in a separate module.
    Every module must have a class called in the same way of the module which
    inherits from this class.
    """

    def __init__(self, parset, name = None, direction = None):
        self.parset = parset
        self.name = name
        self.direction = direction

        self.s = scheduler(max_threads = parset['ncpu'], name = name)
        self.log = logging.getLogger(self.name)

    
    def setup(self):
        if self.direction == None:
            self.log.info('<-- Operation %s started.' % self.name)
        else:
            self.log.info('<-- Operation %s started (direction: %s).' % (self.name, self.direction.name))
        
    def run(self):
        raise(NotImplementedError)

    def finalize(self):
        if self.direction == None:
            self.log.info('--> Operation %s terminated.' % self.name)
        else:
            self.log.info('--> Operation %s terminated (direction: %s).' % (self.name, self.direction.name))
