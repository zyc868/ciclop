'''OpenGL extension EXT.stencil_wrap

Automatically generated by the get_gl_extensions script, do not edit!
'''
from OpenGL import platform, constants, constant, arrays
from OpenGL import extensions
from OpenGL.GL import glget
import ctypes
EXTENSION_NAME = 'GL_EXT_stencil_wrap'
_DEPRECATED = False
GL_INCR_WRAP_EXT = constant.Constant( 'GL_INCR_WRAP_EXT', 0x8507 )
GL_DECR_WRAP_EXT = constant.Constant( 'GL_DECR_WRAP_EXT', 0x8508 )


def glInitStencilWrapEXT():
    '''Return boolean indicating whether this extension is available'''
    return extensions.hasGLExtension( EXTENSION_NAME )