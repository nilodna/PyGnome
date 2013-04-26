'''
Default behavior:
Apply colander monkey patch by default
'''
from gnome.persist import monkey_patch_colander

monkey_patch_colander.apply()


""" 
Define a dict that maps the py_gnome classes or modules to schema modules.
The class names of the schema corresponds with the pyGnome class name.

For instance, 
gnome.model.Model has a corresponding schema gnome.persist.model_schema.Model

This dict just tells us for each pyGnome module or class, where to look for
corresponding schema class
"""
modules_dict= {'gnome.environment':'gnome.persist.environment_schema',
               'gnome.map':'gnome.persist.map_schema',
               'gnome.model':'gnome.persist.model_schema',
               'gnome.movers.movers':'gnome.persist.movers_schema',
               'gnome.spill':'gnome.persist.spills_schema',
               'gnome.renderer':'gnome.persist.outputters_schema'
               }