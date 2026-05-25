//
// chordee-maya Maya module definition
//
// Reads PYTHONPATH from the sibling scripts/python directory so the toolkit
// can be loaded without modifying Maya.env or userSetup.py. To register,
// either drop this directory into MAYA_MODULE_PATH or copy this file into
// Maya's user modules directory (e.g.
// Documents/maya/<version>/modules/ on Windows).
//
+ chordee-maya 0.2.0 ..
PYTHONPATH +:= scripts/python
// Uncomment / create the corresponding directories when adding plug-ins,
// shelves, or icons:
// MAYA_PLUG_IN_PATH +:= plug-ins
// MAYA_SHELF_PATH +:= shelves
// XBMLANGPATH +:= icons
