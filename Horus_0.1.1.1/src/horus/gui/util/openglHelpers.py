#!/usr/bin/python
# -*- coding: utf-8 -*-
#-----------------------------------------------------------------------#
#                                                                       #
# This file is part of the Horus Project                                #
#                                                                       #
# Copyright (C) 2014-2015 Mundo Reader S.L.                             #
# Copyright (C) 2013 David Braam from Cura Project                      #
#                                                                       #
# Date: June 2014                                                       #
# Author: bq Opensource <opensource@bq.com>                    #
#                                                                       #
# This program is free software: you can redistribute it and/or modify  #
# it under the terms of the GNU General Public License as published by  #
# the Free Software Foundation, either version 2 of the License, or     #
# (at your option) any later version.                                   #
#                                                                       #
# This program is distributed in the hope that it will be useful,       #
# but WITHOUT ANY WARRANTY; without even the implied warranty of        #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the          #
# GNU General Public License for more details.                          #
#                                                                       #
# You should have received a copy of the GNU General Public License     #
# along with this program. If not, see <http://www.gnu.org/licenses/>.  #
#                                                                       #
#-----------------------------------------------------------------------#

__author__ = "bq Opensource <opensource@bq.com>"
__license__ = "GNU General Public License v2 http://www.gnu.org/licenses/gpl.html"

import math
import numpy
import wx
import time

from horus.util.resources import getPathForImage

import OpenGL

OpenGL.ERROR_CHECKING = False
from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL.GL import *
from OpenGL.GL import shaders

from sys import platform as _platform
if _platform!='darwin':
	glutInit() #Hack; required before glut can be called. Not required for all OS.

class GLReferenceCounter(object):
	def __init__(self):
		self._refCounter = 1

	def incRef(self):
		self._refCounter += 1

	def decRef(self):
		self._refCounter -= 1
		return self._refCounter <= 0

def hasShaderSupport():
	if bool(glCreateShader):
		return True
	return False

class GLShader(GLReferenceCounter):
	def __init__(self, vertexProgram, fragmentProgram):
		super(GLShader, self).__init__()
		self._vertexString = vertexProgram
		self._fragmentString = fragmentProgram
		try:
			vertexShader = shaders.compileShader(vertexProgram, GL_VERTEX_SHADER)
			fragmentShader = shaders.compileShader(fragmentProgram, GL_FRAGMENT_SHADER)

			#shader.compileProgram tries to return the shader program as a overloaded int. But the return value of a shader does not always fit in a int (needs to be a long). So we do raw OpenGL calls.
			# This is to ensure that this works on intel GPU's
			# self._program = shaders.compileProgram(self._vertexProgram, self._fragmentProgram)
			self._program = glCreateProgram()
			glAttachShader(self._program, vertexShader)
			glAttachShader(self._program, fragmentShader)
			glLinkProgram(self._program)
			# Validation has to occur *after* linking
			glValidateProgram(self._program)
			if glGetProgramiv(self._program, GL_VALIDATE_STATUS) == GL_FALSE:
				raise RuntimeError("Validation failure: %s"%(glGetProgramInfoLog(self._program)))
			if glGetProgramiv(self._program, GL_LINK_STATUS) == GL_FALSE:
				raise RuntimeError("Link failure: %s" % (glGetProgramInfoLog(self._program)))
			glDeleteShader(vertexShader)
			glDeleteShader(fragmentShader)
		except RuntimeError, e:
			print str(e)
			self._program = None

	def bind(self):
		if self._program is not None:
			shaders.glUseProgram(self._program)

	def unbind(self):
		shaders.glUseProgram(0)

	def release(self):
		if self._program is not None:
			glDeleteProgram(self._program)
			self._program = None

	def setUniform(self, name, value):
		if self._program is not None:
			if type(value) is float:
				glUniform1f(glGetUniformLocation(self._program, name), value)
			elif type(value) is numpy.matrix:
				glUniformMatrix3fv(glGetUniformLocation(self._program, name), 1, False, value.getA().astype(numpy.float32))
			else:
				print 'Unknown type for setUniform: %s' % (str(type(value)))

	def isValid(self):
		return self._program is not None

	def getVertexShader(self):
		return self._vertexString

	def getFragmentShader(self):
		return self._fragmentString

	def __del__(self):
		if self._program is not None and bool(glDeleteProgram):
			print "Shader was not properly released!"

class GLFakeShader(GLReferenceCounter):
	"""
	A Class that acts as an OpenGL shader, but in reality is not one. Used if shaders are not supported.
	"""
	def __init__(self):
		super(GLFakeShader, self).__init__()

	def bind(self):
		glEnable(GL_LIGHTING)
		glEnable(GL_LIGHT0)
		glEnable(GL_COLOR_MATERIAL)
		glLightfv(GL_LIGHT0, GL_DIFFUSE, [1,1,1,1])
		glLightfv(GL_LIGHT0, GL_AMBIENT, [0,0,0,0])
		glLightfv(GL_LIGHT0, GL_SPECULAR, [0,0,0,0])

	def unbind(self):
		glDisable(GL_LIGHTING)

	def release(self):
		pass

	def setUniform(self, name, value):
		pass

	def isValid(self):
		return True

	def getVertexShader(self):
		return ''

	def getFragmentShader(self):
		return ''

class GLVBO(GLReferenceCounter):
	"""
	Vertex buffer object. Used for faster rendering.
	"""
	def __init__(self, renderType, vertexArray, normalArray = None, indicesArray = None, colorArray = None):
		super(GLVBO, self).__init__()
		self._renderType = renderType
		if not bool(glGenBuffers): # Fallback if buffers are not supported.
			self._vertexArray = vertexArray
			self._normalArray = normalArray
			self._indicesArray = indicesArray
			self._colorArray = colorArray
			self._size = len(vertexArray)
			self._buffer = None
			self._hasNormals = self._normalArray is not None
			self._hasIndices = self._indicesArray is not None
			self._hasColor = self._colorArray is not None
			if self._hasIndices:
				self._size = len(indicesArray)
		else:
			self._size = len(vertexArray)
			self._hasNormals = normalArray is not None
			self._hasIndices = indicesArray is not None
			self._hasColor = colorArray is not None
			if self._hasNormals: #TODO: Add size check to see if arrays have same size.
				self._buffer = glGenBuffers(1)
				glBindBuffer(GL_ARRAY_BUFFER, self._buffer)
				glBufferData(GL_ARRAY_BUFFER, numpy.concatenate((vertexArray, normalArray), 1), GL_STATIC_DRAW)
			else:
				if self._hasColor:
					glPointSize(2)
					self._buffer = glGenBuffers(2)
					glBindBuffer(GL_ARRAY_BUFFER, self._buffer[0])
					glBufferData(GL_ARRAY_BUFFER, vertexArray, GL_STATIC_DRAW)
					glBindBuffer(GL_ARRAY_BUFFER, self._buffer[1])
					glBufferData(GL_ARRAY_BUFFER, numpy.array(colorArray, numpy.uint8), GL_STATIC_DRAW)
				else:
					self._buffer = glGenBuffers(1)
					glBindBuffer(GL_ARRAY_BUFFER, self._buffer)
					glBufferData(GL_ARRAY_BUFFER, vertexArray, GL_STATIC_DRAW)

			glBindBuffer(GL_ARRAY_BUFFER, 0)
			if self._hasIndices:
				self._size = len(indicesArray)
				self._bufferIndices = glGenBuffers(1)
				glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._bufferIndices)
				glBufferData(GL_ELEMENT_ARRAY_BUFFER, numpy.array(indicesArray, numpy.uint32), GL_STATIC_DRAW)

	def render(self):
		glEnableClientState(GL_VERTEX_ARRAY)
		if self._buffer is None:
			glVertexPointer(3, GL_FLOAT, 0, self._vertexArray)
			if self._hasNormals:
				glEnableClientState(GL_NORMAL_ARRAY)
				glNormalPointer(GL_FLOAT, 0, self._normalArray)
			if self._hasColor:
				glEnableClientState(GL_COLOR_ARRAY)
				glColorPointer(3, GL_UNSIGNED_BYTE, 0, self._colorArray)
		else:
			if self._hasNormals:
				glBindBuffer(GL_ARRAY_BUFFER, self._buffer)
				glEnableClientState(GL_NORMAL_ARRAY)
				glVertexPointer(3, GL_FLOAT, 2*3*4, c_void_p(0))
				glNormalPointer(GL_FLOAT, 2*3*4, c_void_p(3 * 4))
			else:
				if self._hasColor:
					glEnableClientState(GL_COLOR_ARRAY)
					glBindBuffer(GL_ARRAY_BUFFER, self._buffer[1])
					glColorPointer(3, GL_UNSIGNED_BYTE, 0, None)
					glBindBuffer(GL_ARRAY_BUFFER, self._buffer[0])
					glVertexPointer(3, GL_FLOAT, 0, None)
				else:
					glBindBuffer(GL_ARRAY_BUFFER, self._buffer)
					glVertexPointer(3, GL_FLOAT, 3*4, c_void_p(0))

			if self._hasIndices:
				glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._bufferIndices)

		if self._hasIndices:
			if self._buffer is None:
				glDrawElements(self._renderType, self._size, GL_UNSIGNED_INT, self._indicesArray)
			else:
				glDrawElements(self._renderType, self._size, GL_UNSIGNED_INT, c_void_p(0))
		else:
			batchSize = 996    #Warning, batchSize needs to be dividable by 4 (quads), 3 (triangles) and 2 (lines). Current value is magic.
			extraStartPos = int(self._size / batchSize) * batchSize #leftovers.
			extraCount = self._size - extraStartPos
			for i in xrange(0, int(self._size / batchSize)):
				glDrawArrays(self._renderType, i * batchSize, batchSize)
			glDrawArrays(self._renderType, extraStartPos, extraCount)

		if self._buffer is not None:
			glBindBuffer(GL_ARRAY_BUFFER, 0)
		if self._hasIndices:
			glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)

		if self._hasNormals:
			glDisableClientState(GL_NORMAL_ARRAY)
		if self._hasColor:
			glDisableClientState(GL_COLOR_ARRAY)
		glDisableClientState(GL_VERTEX_ARRAY)

	def release(self):
		if self._buffer is not None:
			if self._hasColor:
				glBindBuffer(GL_ARRAY_BUFFER, self._buffer[0])
				glBufferData(GL_ARRAY_BUFFER, None, GL_STATIC_DRAW)
				glBindBuffer(GL_ARRAY_BUFFER, 0)
				glDeleteBuffers(1, [self._buffer[0]])
				glBindBuffer(GL_ARRAY_BUFFER, self._buffer[1])
				glBufferData(GL_ARRAY_BUFFER, None, GL_STATIC_DRAW)
				glBindBuffer(GL_ARRAY_BUFFER, 0)
				glDeleteBuffers(1, [self._buffer[1]])
				self._buffer = None
			else:
				glBindBuffer(GL_ARRAY_BUFFER, self._buffer)
				glBufferData(GL_ARRAY_BUFFER, None, GL_STATIC_DRAW)
				glBindBuffer(GL_ARRAY_BUFFER, 0)
				glDeleteBuffers(1, [self._buffer])
				self._buffer = None
			if self._hasIndices:
				glBindBuffer(GL_ARRAY_BUFFER, self._bufferIndices)
				glBufferData(GL_ARRAY_BUFFER, None, GL_STATIC_DRAW)
				glBindBuffer(GL_ARRAY_BUFFER, 0)
				glDeleteBuffers(1, [self._bufferIndices])
		self._vertexArray = None
		self._normalArray = None

	def __del__(self):
		if self._buffer is not None and bool(glDeleteBuffers):
			print "VBO was not properly released!"

def glDrawStringCenter(s):
	"""
	Draw string on current draw pointer position
	"""
	glRasterPos2f(0, 0)
	glBitmap(0,0,0,0, -glGetStringSize(s)[0]/2, 0, None)
	for c in s:
		glutBitmapCharacter(OpenGL.GLUT.GLUT_BITMAP_HELVETICA_18, ord(c))

def glGetStringSize(s):
	"""
	Get size in pixels of string
	"""
	width = 0
	for c in s:
		width += glutBitmapWidth(OpenGL.GLUT.GLUT_BITMAP_HELVETICA_18, ord(c))
	height = 18
	return width, height

def glDrawStringLeft(s):
	glRasterPos2f(0, 0)
	n = 1
	for c in s:
		if c == '\n':
			glPushMatrix()
			glTranslate(0, 18 * n, 0)
			n += 1
			glRasterPos2f(0, 0)
			glPopMatrix()
		else:
			glutBitmapCharacter(OpenGL.GLUT.GLUT_BITMAP_HELVETICA_18, ord(c))

def glDrawStringRight(s):
	glRasterPos2f(0, 0)
	glBitmap(0,0,0,0, -glGetStringSize(s)[0], 0, None)
	for c in s:
		glutBitmapCharacter(OpenGL.GLUT.GLUT_BITMAP_HELVETICA_18, ord(c))

def glDrawQuad(x, y, w, h):
	glPushMatrix()
	glTranslatef(x, y, 0)
	glDisable(GL_TEXTURE_2D)
	glBegin(GL_QUADS)
	glVertex2f(w, 0)
	glVertex2f(0, 0)
	glVertex2f(0, h)
	glVertex2f(w, h)
	glEnd()
	glPopMatrix()

def glDrawTexturedQuad(x, y, w, h, texID, mirror = 0):
	tx = float(texID % 4) / 4
	ty = float(int(texID / 4)) / 8
	tsx = 0.25
	tsy = 0.125
	if mirror & 1:
		tx += tsx
		tsx = -tsx
	if mirror & 2:
		ty += tsy
		tsy = -tsy
	glPushMatrix()
	glTranslatef(x, y, 0)
	glEnable(GL_TEXTURE_2D)
	glBegin(GL_QUADS)
	glTexCoord2f(tx+tsx, ty)
	glVertex2f(w, 0)
	glTexCoord2f(tx, ty)
	glVertex2f(0, 0)
	glTexCoord2f(tx, ty+tsy)
	glVertex2f(0, h)
	glTexCoord2f(tx+tsx, ty+tsy)
	glVertex2f(w, h)
	glEnd()
	glPopMatrix()

def glDrawStretchedQuad(x, y, w, h, cornerSize, texID):
	"""
	Same as draw texured quad, but without stretching the corners. Useful for resizable windows.
	"""
	tx0 = float(texID % 4) / 4
	ty0 = float(int(texID / 4)) / 8
	tx1 = tx0 + 0.25 / 2.0
	ty1 = ty0 + 0.125 / 2.0
	tx2 = tx0 + 0.25
	ty2 = ty0 + 0.125

	glPushMatrix()
	glTranslatef(x, y, 0)
	glEnable(GL_TEXTURE_2D)
	glBegin(GL_QUADS)
	#TopLeft
	glTexCoord2f(tx1, ty0)
	glVertex2f( cornerSize, 0)
	glTexCoord2f(tx0, ty0)
	glVertex2f( 0, 0)
	glTexCoord2f(tx0, ty1)
	glVertex2f( 0, cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, cornerSize)
	#TopRight
	glTexCoord2f(tx2, ty0)
	glVertex2f( w, 0)
	glTexCoord2f(tx1, ty0)
	glVertex2f( w - cornerSize, 0)
	glTexCoord2f(tx1, ty1)
	glVertex2f( w - cornerSize, cornerSize)
	glTexCoord2f(tx2, ty1)
	glVertex2f( w, cornerSize)
	#BottomLeft
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, h - cornerSize)
	glTexCoord2f(tx0, ty1)
	glVertex2f( 0, h - cornerSize)
	glTexCoord2f(tx0, ty2)
	glVertex2f( 0, h)
	glTexCoord2f(tx1, ty2)
	glVertex2f( cornerSize, h)
	#BottomRight
	glTexCoord2f(tx2, ty1)
	glVertex2f( w, h - cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( w - cornerSize, h - cornerSize)
	glTexCoord2f(tx1, ty2)
	glVertex2f( w - cornerSize, h)
	glTexCoord2f(tx2, ty2)
	glVertex2f( w, h)

	#Center
	glTexCoord2f(tx1, ty1)
	glVertex2f( w-cornerSize, cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, h-cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( w-cornerSize, h-cornerSize)

	#Right
	glTexCoord2f(tx2, ty1)
	glVertex2f( w, cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( w-cornerSize, cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( w-cornerSize, h-cornerSize)
	glTexCoord2f(tx2, ty1)
	glVertex2f( w, h-cornerSize)

	#Left
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, cornerSize)
	glTexCoord2f(tx0, ty1)
	glVertex2f( 0, cornerSize)
	glTexCoord2f(tx0, ty1)
	glVertex2f( 0, h-cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, h-cornerSize)

	#Top
	glTexCoord2f(tx1, ty0)
	glVertex2f( w-cornerSize, 0)
	glTexCoord2f(tx1, ty0)
	glVertex2f( cornerSize, 0)
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( w-cornerSize, cornerSize)

	#Bottom
	glTexCoord2f(tx1, ty1)
	glVertex2f( w-cornerSize, h-cornerSize)
	glTexCoord2f(tx1, ty1)
	glVertex2f( cornerSize, h-cornerSize)
	glTexCoord2f(tx1, ty2)
	glVertex2f( cornerSize, h)
	glTexCoord2f(tx1, ty2)
	glVertex2f( w-cornerSize, h)

	glEnd()
	glDisable(GL_TEXTURE_2D)
	glPopMatrix()

def unproject(winx, winy, winz, modelMatrix, projMatrix, viewport):
	"""
	Projects window position to 3D space. (gluUnProject). Reimplentation as some drivers crash with the original.
	"""
	npModelMatrix = numpy.matrix(numpy.array(modelMatrix, numpy.float64).reshape((4,4)))
	npProjMatrix = numpy.matrix(numpy.array(projMatrix, numpy.float64).reshape((4,4)))
	finalMatrix = npModelMatrix * npProjMatrix
	finalMatrix = numpy.linalg.inv(finalMatrix)

	viewport = map(float, viewport)
	if viewport[2] > 0 and viewport[3] > 0:
		vector = numpy.array([(winx - viewport[0]) / viewport[2] * 2.0 - 1.0, (winy - viewport[1]) / viewport[3] * 2.0 - 1.0, winz * 2.0 - 1.0, 1]).reshape((1,4))
		vector = (numpy.matrix(vector) * finalMatrix).getA().flatten()
		ret = list(vector)[0:3] / vector[3]
		return ret

def convert3x3MatrixTo4x4(matrix):
	return list(matrix.getA()[0]) + [0] + list(matrix.getA()[1]) + [0] + list(matrix.getA()[2]) + [0, 0,0,0,1]

def loadGLTexture(filename):
	tex = glGenTextures(1)
	glBindTexture(GL_TEXTURE_2D, tex)
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
	img = wx.ImageFromBitmap(wx.Bitmap(getPathForImage(filename)))
	rgbData = img.GetData()
	alphaData = img.GetAlphaData()
	if alphaData is not None:
		data = ''
		for i in xrange(0, len(alphaData)):
			data += rgbData[i*3:i*3+3] + alphaData[i]
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.GetWidth(), img.GetHeight(), 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
	else:
		glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.GetWidth(), img.GetHeight(), 0, GL_RGB, GL_UNSIGNED_BYTE, rgbData)
	return tex

def DrawBox(vMin, vMax):
	""" Draw wireframe box
	"""
	glBegin(GL_LINE_LOOP)
	glVertex3f(vMin[0], vMin[1], vMin[2])
	glVertex3f(vMax[0], vMin[1], vMin[2])
	glVertex3f(vMax[0], vMax[1], vMin[2])
	glVertex3f(vMin[0], vMax[1], vMin[2])
	glEnd()

	glBegin(GL_LINE_LOOP)
	glVertex3f(vMin[0], vMin[1], vMax[2])
	glVertex3f(vMax[0], vMin[1], vMax[2])
	glVertex3f(vMax[0], vMax[1], vMax[2])
	glVertex3f(vMin[0], vMax[1], vMax[2])
	glEnd()
	glBegin(GL_LINES)
	glVertex3f(vMin[0], vMin[1], vMin[2])
	glVertex3f(vMin[0], vMin[1], vMax[2])
	glVertex3f(vMax[0], vMin[1], vMin[2])
	glVertex3f(vMax[0], vMin[1], vMax[2])
	glVertex3f(vMax[0], vMax[1], vMin[2])
	glVertex3f(vMax[0], vMax[1], vMax[2])
	glVertex3f(vMin[0], vMax[1], vMin[2])
	glVertex3f(vMin[0], vMax[1], vMax[2])
	glEnd()