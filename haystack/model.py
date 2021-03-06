#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Loic Jaquemet loic.jaquemet+python@gmail.com
#

'''
This module is the main aspect of haystack.
The whole point of this module is to search a memory space for a valid 
C structure.
'Valid' means:
  * a pointer should have a pointer value.
  * a string whould be a string.
  * a constrainged integer should be in a range of acceptable values.
  etc...

You can implement your own structures easily by registering your module 
containing ctypes Structure :

  # mymodule.py
  from haystack import model
  
  [... structure definition .. ]
  
  model.registerModule(sys.modules[__name__])

--------------------------------------------------------------------------------

Structure definition is done strictly within ctypes habits.
But as a bonus, you can add some constraints on the structure members by adding
a member expectedValues on the Python object.

Example :

  # ctypes_openssl.py
  from haystack import model

  class RSA(OpenSSLStruct):
    """ rsa/rsa.h """
    _fields_ = [
    ("pad",  ctypes.c_int), 
    ("version",  ctypes.c_long),
    ("meth",ctypes.POINTER(BIGNUM)),#const RSA_METHOD *meth;
    ("engine",ctypes.POINTER(ENGINE)),#ENGINE *engine;
    ('n', ctypes.POINTER(BIGNUM) ), ## still in ssh memap
    ('e', ctypes.POINTER(BIGNUM) ), ## still in ssh memap
    ('d', ctypes.POINTER(BIGNUM) ), ## still in ssh memap
    ('p', ctypes.POINTER(BIGNUM) ), ## still in ssh memap
    ('q', ctypes.POINTER(BIGNUM) ), ## still in ssh memap
    ('dmp1', ctypes.POINTER(BIGNUM) ),
    ('dmq1', ctypes.POINTER(BIGNUM) ),
    ('iqmp', ctypes.POINTER(BIGNUM) ),
    ("ex_data", CRYPTO_EX_DATA ),
    ("references", ctypes.c_int),
    ("flags", ctypes.c_int),
    ("_method_mod_n", ctypes.POINTER(BN_MONT_CTX) ),
    ("_method_mod_p", ctypes.POINTER(BN_MONT_CTX) ),
    ("_method_mod_q", ctypes.POINTER(BN_MONT_CTX) ),
    ("bignum_data",ctypes.POINTER(ctypes.c_ubyte)), ## moue c_char_p ou POINTER(c_char) ?
    ("blinding",ctypes.POINTER(BIGNUM)),#BN_BLINDING *blinding;
    ("mt_blinding",ctypes.POINTER(BIGNUM))#BN_BLINDING *mt_blinding;
    ]
    expectedValues={
      "pad": [0], 
      "version": [0], 
      "references": RangeValue(0,0xfff),
      "n": [NotNull],
      "e": [NotNull],
      "d": [NotNull],
      "p": [NotNull],
      "q": [NotNull],
      "dmp1": [NotNull],
      "dmq1": [NotNull],
      "iqmp": [NotNull]
    }
    def loadMembers(self, mappings, maxDepth):
      if not LoadableMembers.loadMembers(self, mappings, maxDepth):
        log.debug('RSA not loaded')
        return False
      return True

  # register to haystack
  model.registerModule(sys.modules[__name__])

--------------------------------------------------------------------------------

As an added bonus, you can also use ctypeslib code generator to autogenerate 
ctypes python structure from C headers.
You should have a look into that : h2py && xml2py 
Anyway, haystack will support you with your generated headers.
Put the generated headers in a separate file, and put your expected values in an
other file. You can then register the autogenerated module.

Example :

  # generated headers are in ctypes_putty_generated.py
  # ctypes_putty.py
  import ctypes_putty_generated as gen

  ################ START copy generated classes ##########################
  # copy generated classes (gen.*) to this module as wrapper
  model.copyGeneratedClasses(gen, sys.modules[__name__])

  # register all classes (gen.*, locally defines, and local duplicates) to haystack
  # create plain old python object from ctypes.Structure's, to picke them
  model.registerModule(sys.modules[__name__])

  RSAKey.expectedValues={
      'bits': [NotNull],
      'bytes': [NotNull],
      'modulus': [NotNull],
      'exponent': [NotNull],
      'private_exponent': [NotNull],
      'p': [NotNull],
      'q': [NotNull],
      'iqmp': [NotNull]
    }
  [... loads of constraints on putty structures... ]

--------------------------------------------------------------------------------

Enjoy.

'''

import ctypes
import logging
from haystack.utils import *

__author__ = "Loic Jaquemet"
__copyright__ = "Copyright (C) 2012 Loic Jaquemet"
__email__ = "loic.jaquemet+python@gmail.com"
__license__ = "GPL"
__maintainer__ = "Loic Jaquemet"
__status__ = "Production"

log = logging.getLogger('model')

# replace c_char_p so we can have our own CString 
if ctypes.c_char_p.__name__ == 'c_char_p':
  ctypes.original_c_char_p = ctypes.c_char_p

# keep orig class and Use our model instead as base Structure class
if ctypes.Structure.__name__ == 'Structure':
  ctypes.original_Structure = ctypes.Structure

# The book registers all haystack modules, and classes, and can keep 
# some pointer refs on memory allocated within special cases...
class _book(object):
  modules = set()
  classes = dict()
  refs = dict()
  def __init__(self):
    pass
  def addModule(self, mod):
    self.modules.add(mod)
  def addClass(self,cls):
    self.classes[ctypes.POINTER(cls)] = cls
  def addRef(self,obj, typ, addr):
    self.refs[(typ,addr)]=obj
  def getModules(self):
    return set(self.modules)
  def getClasses(self):
    return dict(self.classes)
  def getRef(self,typ,addr):
    return self.refs[(typ,addr)]
  def delRef(self,typ,addr):
    del self.refs[(typ,addr)]
  def isRegisteredType(self, typ):
    return typ in self.classes.values()

    
# central model book register
__book = _book()

def printRefs():
  l=[(typ,obj,addr) for ((typ,addr),obj) in __book.refs.items()]
  for i in l:
    print l

def hasRef(typ,origAddr):
  return (typ,origAddr) in __book.refs

def getRef(typ,origAddr):
  if (typ,origAddr) in __book.refs:
    return __book.getRef(typ,origAddr)
  return None

def keepRef(obj,typ=None,origAddr=None):
  ''' Sometypes, your have to cast a c_void_p, You can keep ref in Ctypes object, 
    they might be transient (if obj == somepointer.contents).'''
  if (typ,origAddr) in __book.refs:
    # ADDRESS already in refs
    if origAddr is None:
      origAddr='None'
    else:
      origAddr=hex(origAddr)
    if typ is not None:
      log.debug('references already in cache %s/%s'%(typ,origAddr))
    return
  __book.addRef(obj,typ,origAddr)
  return

def delRef(typ,origAddr):
  ''' Forget about a Ref..'''
  if (typ,origAddr) in __book.refs:
    __book.delRef(typ,origAddr)
  return

def register(klass):
  #klass.classRef = __register
  #__register[ctypes.POINTER(klass)] = klass
  __book.addClass(klass)
  klass.classRef = __book.classes
  return klass

def registeredModules():
  return sys.modules[__name__].__book.getModules()


class CString(ctypes.Union):
  ''' 
  This is our own implementation of a string for ctypes.
  ctypes.c_char_p can not be used for memory parsing, as it tries to load 
  the string itself without checking for pointer validation.
  
  it's basically a Union of a string and a pointer.
  '''
  _fields_=[
  ("string", ctypes.original_c_char_p),
  ("ptr", ctypes.POINTER(ctypes.c_ubyte) )
  ]
  def toString(self):
    if not bool(self.ptr):
      return "<NULLPTR>"
    return self.string
  pass


class LoadableMembers(ctypes.Structure):
  ''' 
  This is the main class, to be inherited by all ctypes structure.
  It adds a generic validaiton framework, based on simple assertion, 
  and on more complex constraint on members values.
    
  '''
  classRef=dict()
  expectedValues=dict()
  
  ''' 
    Iterate over the fields and types of this structure, including inherited ones.
  '''
  def getFields(self):
    return type(self).getFields()
  
  @classmethod
  def getFields(cls):
    mro = cls.mro()[:-3] # cut Structure, _CData and object
    mro.reverse()
    me = mro.pop(-1)
    for typ in mro: # firsts are first, cls is in here in [-1]
      if not hasattr(typ, '_fields_'):
        continue
      for name,vtyp in typ.getFields():
        #yield ('%s_%s'%(typ.__name__, name), vtyp)
        yield (name, vtyp)
    # print mines.
    for f in me._fields_:
      yield (f[0],f[1])
    
    raise StopIteration

  def isValid(self,mappings):
    ''' 
    Checks if each members has coherent data 

    For each Field, check on of the three case, 
      a) basic types (check for expectedValues), 
        if field as some expected values in expectedValues
           check field value against expectedValues[fieldname]
           if False, return False, else continue
      
      b) struct(check isValid) 
        check if the inner struct isValid()
        if False, return False, else continue
      
      c) is an array , recurse validation
      
      d) Pointer(check valid_address or expectedValues is None == NULL )
        if field as some expected values in expectedValues 
          ( None or 0 ) are the only valid options to design NULL pointers
           check field getaddress() value against expectedValues[fieldname] // if NULL
              if True(address is NULL and it's a valid value), continue
           check getaddress against is_valid_address() 
              if False, return False, else continue
    '''
    valid = self._isValid(mappings)
    log.debug('%s isValid = %s'%(self.__class__.__name__,valid))
    return valid

  def _isValid(self,mappings):
    ''' real implementation.  check expectedValues first, then the other fields '''
    log.debug(' ------ isValid ----------')
    _fieldsTuple = self.getFields()
    myfields=dict(_fieldsTuple)
    done=[]
    # check expectedValues first
    for attrname, expected in self.expectedValues.iteritems():
      attrtype = myfields[attrname]
      attr=getattr(self,attrname)
      if expected is IgnoreMember:
        continue
      if not self._isValidAttr(attr,attrname,attrtype,mappings):
        return False
      done.append(attrname)
    # check the rest for validation
    todo = [ (name, typ) for name,typ in self.getFields() if name not in done ]
    for attrname,attrtype, in todo:
      attr=getattr(self,attrname)
      if attrname in self.expectedValues:
        if self.expectedValues[attrname] is IgnoreMember:
          continue
      if not self._isValidAttr(attr,attrname,attrtype,mappings):
        return False
    # validation done
    return True
    
  def _isValidAttr(self,attr,attrname,attrtype,mappings):
    ''' Validation of a single member '''
    # a) 
    log.debug('valid: %s'%(attrtype))
    if isBasicType(attrtype):
      if attrname in self.expectedValues:
        if attr not in self.expectedValues[attrname]:
          log.debug('basicType: %s %s %s bad value not in self.expectedValues[attrname]:'%(attrname,attrtype,repr(attr) ))
          return False
      log.debug('basicType: %s %s %s ok'%(attrname,attrtype,repr(attr) ))
      return True
    # b)
    if isStructType(attrtype):
      ### do i need to load it first ? becaus it should be memcopied with the super()..
      if not attr.isValid(mappings):
        log.debug('structType: %s %s %s isValid FALSE'%(attrname,attrtype,repr(attr) ))
        return False
      log.debug('structType: %s %s %s isValid TRUE'%(attrname,attrtype,repr(attr) ))
      return True
    # c)
    if isBasicTypeArray(attr):
      if attrname in self.expectedValues:
        if attr not in self.expectedValues[attrname]:
          log.debug('basicArray: %s %s %s bad value not in self.expectedValues[attrname]:'%(attrname,attrtype,repr(attr) ))
          return False
      log.debug('basicArray: %s is arraytype %s we decided it was valid',attrname,repr(attr))#
      return True
    if isArrayType(attrtype):
      log.debug('array: %s is arraytype %s recurse validate'%(attrname,repr(attr)) )#
      attrLen=len(attr)
      if attrLen == 0:
        return True
      elType=type(attr[0])
      for i in range(0,attrLen):
        if not self._isValidAttr(attr[i], "%s[%d]"%(attrname,i), elType, mappings ):
          return False
      return True
    # d)
    if isCStringPointer(attrtype):
      myaddress=getaddress(attr.ptr)
      if attrname in self.expectedValues:
        # test if NULL is an option
        if not bool(myaddress) :
          if not ( (None in self.expectedValues[attrname]) or
                   (0 in self.expectedValues[attrname]) ):
            log.debug('str: %s %s %s isNULL and that is NOT EXPECTED'%(attrname,attrtype,repr(attr) ))
            return False
          log.debug('str: %s %s %s isNULL and that is OK'%(attrname,attrtype,repr(attr) ))
          return True
      if (myaddress != 0) and ( not is_valid_address_value( myaddress, mappings) )   :
        log.debug('str: %s %s %s 0x%lx INVALID'%(attrname,attrtype, repr(attr) ,myaddress))
        return False
      log.debug('str: %s %s %s is at 0x%lx OK'%(attrname,attrtype,repr(attr),myaddress ))
      return True
    # e) 
    if isPointerType(attrtype):
      if attrname in self.expectedValues:
        # test if NULL is an option
        log.debug('isPointerType: bool(attr):%s attr:%s'%(bool(attr), attr))
        if not bool(attr):
          if not ( (None in self.expectedValues[attrname]) or
                   (0 in self.expectedValues[attrname]) ):
            log.debug('ptr: %s %s %s isNULL and that is NOT EXPECTED'%(attrname,attrtype,repr(attr) ))
            return False
          log.debug('ptr: %s %s %s isNULL and that is OK'%(attrname,attrtype,repr(attr) ))
          return True
      # all case, 
      _attrType=None
      if isVoidPointerType(attrtype):
        log.debug('Its a simple type. Checking mappings only.')
        if getaddress(attr) != 0 and not is_valid_address_value( attr, mappings): # NULL can be accepted
          log.debug('voidptr: %s %s %s 0x%lx INVALID simple pointer'%(attrname,attrtype, repr(attr) ,getaddress(attr)))
          return False
      elif attrtype not in self.classRef:
        log.debug("I can't know the size of the basic type behind the %s pointer, it's not a pointer to known registered struct type"%(attrname))
        _attrType=None
      else:
        # test valid address mapping
        _attrType=self.classRef[attrtype]
      #log.debug(" ihave decided on pointed attrType to be %s"%(_attrType))
      if ( not is_valid_address( attr, mappings, _attrType) ) and (getaddress(attr) != 0):
        log.debug('ptr: %s %s %s 0x%lx INVALID'%(attrname,attrtype, repr(attr) ,getaddress(attr)))
        return False
      # null is accepted by default 
      log.debug('ptr: %s %s 0x%lx OK'%(attrname,repr(attr) ,getaddress(attr)))
      return True
    # ?
    if isUnionType(attrtype):
      #log.warning('Union are not validated , yet ')
      return True
    log.error('What type are You ?: %s/%s'%(attrname,attrtype))
    return True

  def _isLoadableMember(self, attr):
    '''
      Check if the member is loadable.
      A c_void_p cannot be load generically, You have to take care of that.
    '''
    attrtype=type(attr)
    return ( (isPointerType(attrtype) and ( attrtype in self.classRef) and bool(attr) and not isFunctionType(attrtype) ) or
              isStructType(attrtype)  or isCStringPointer(attrtype) or
              (isArrayType(attrtype) and not isBasicTypeArray(attr) ) ) # should we iterate on Basictypes ? no

  def loadMembers(self, mappings, maxDepth):
    ''' 
    The validity of the memebrs will be assessed.
    Each members that can be ( structures, pointers), will be evaluated for validity and loaded recursively.
    
    @param mappings: list of memoryMappings for the process.
    @param maxDepth: limitation of depth after which the loading/validation will stop and return results.

    @returns True if everything has been loaded, False if something went wrong. 
    '''
    if maxDepth == 0:
      log.debug('Maximum depth reach. Not loading any deeper members.')
      log.debug('Struct partially LOADED. %s not loaded'%(self.__class__.__name__))
      return True
    maxDepth-=1
    log.debug('%s loadMembers'%(self.__class__.__name__))
    if not self.isValid(mappings):
      return False
    log.debug('%s do loadMembers ----------------'%(self.__class__.__name__))
    ## go through all members. if they are pointers AND not null AND in valid memorymapping AND a struct type, load them as struct pointers
    for attrname,attrtype in self.getFields():
      attr=getattr(self,attrname)
      # shorcut ignores
      if attrname in self.expectedValues:
        # shortcut
        if self.expectedValues[attrname] is IgnoreMember:
          # make an new empty ctypes
          setattr(self, attrname, attrtype())
          return True      
      try:
        if not self._loadMember(attr,attrname,attrtype,mappings, maxDepth):
          return False
      except ValueError, e:
        log.error( 'maxDepth was %d'% maxDepth)
        raise e

    log.debug('%s END loadMembers ----------------'%(self.__class__.__name__))
    return True
    
  def _loadMember(self,attr,attrname,attrtype,mappings, maxDepth):
    # skip static basic data members
    if not self._isLoadableMember(attr):
      log.debug("%s %s not loadable  bool(attr) = %s"%(attrname,attrtype, bool(attr)) )
      return True
    # load it, fields are valid
    if isStructType(attrtype):
      log.debug('st: %s %s is STRUCT'%(attrname,attrtype) )
      if not attr.loadMembers(mappings, maxDepth+1):
        log.debug("st: %s %s not valid, erreur while loading inner struct "%(attrname,attrtype) )
        return False
      log.debug("st: %s %s inner struct LOADED "%(attrname,attrtype) )
      return True
    # maybe an array
    if isBasicTypeArray(attr):
      return True
    if isArrayType(attrtype):
      log.debug('a: %s is arraytype %s recurse load'%(attrname,repr(attr)) )#
      attrLen=len(attr)
      if attrLen == 0:
        return True
      elType=type(attr[0])
      for i in range(0,attrLen):
        if not self._loadMember(attr[i], "%s[%d]"%(attrname,i), elType, mappings, maxDepth):
          return False
      return True
    # we have PointerType here . Basic or complex
    # exception cases
    if isCStringPointer(attrtype) : 
      # can't use basic c_char_p because we can't load in foreign memory
      attr_obj_address = getaddress(attr.ptr)
      setattr(self,'__'+attrname,attr_obj_address)
      if not bool(attr_obj_address):
        log.debug('%s %s is a CString, the pointer is null (validation must have occurred earlier) '%(attrname, attr))
        return True
      memoryMap = is_valid_address_value(attr_obj_address, mappings)
      if not memoryMap :
        log.warning('Error on addr while fetching a CString. should not happen')
        return False
      MAX_SIZE=255
      log.debug("%s %s is defined as a CString, loading from 0x%lx is_valid_address %s"%(
                      attrname,attr,attr_obj_address, is_valid_address(attr,mappings) ))
      txt,full = memoryMap.readCString(attr_obj_address, MAX_SIZE )
      if not full:
        log.warning('buffer size was too small for this CString')
      attr.string = txt
      return True
    elif isPointerType(attrtype): # not functionType, it's not loadable
      _attrname='_'+attrname
      _attrType=self.classRef[attrtype]
      attr_obj_address=getaddress(attr)
      setattr(self,'__'+attrname,attr_obj_address)
      ####
      # memcpy and save objet ref + pointer in attr
      # we know the field is considered valid, so if it's not in memory_space, we can ignore it
      memoryMap = is_valid_address( attr, mappings, _attrType)
      if(not memoryMap):
        # big BUG Badaboum, why did pointer changed validity/value ?
        log.warning("%s %s not loadable 0x%lx but VALID "%(attrname, attr,attr_obj_address ))
        return True
      ref=getRef(_attrType,attr_obj_address)
      if ref:
        log.debug("%s %s loading from references cache %s/0x%lx"%(attrname,attr,_attrType,attr_obj_address ))
        attr.contents = ref
        return True
      log.debug("%s %s loading from 0x%lx (is_valid_address: %s)"%(attrname,attr,attr_obj_address, memoryMap ))
      ##### Read the struct in memory and make a copy to play with.
      attr.contents=_attrType.from_buffer_copy(memoryMap.readStruct(attr_obj_address, _attrType ))
      # save that validated and loaded ref and original addr so we dont need to recopy it later
      keepRef( attr.contents, _attrType, attr_obj_address)
      log.debug("%s %s loaded memcopy from 0x%lx to 0x%lx"%(attrname, attr, attr_obj_address, (getaddress(attr))   ))
      # recursive validation checks on new struct
      if not bool(attr):
        log.warning('Member %s is null after copy: %s'%(attrname,attr))
        return True
      # go and load the pointed struct members recursively
      if not attr.contents.loadMembers(mappings, maxDepth):
        log.debug('member %s was not loaded'%(attrname))
        #invalidate the cache ref.
        delRef( _attrType, attr_obj_address)
        return False
      return True
    #TATAFN
    return True
  
  def toString(self,prefix=''):
    ''' Returns a string formatted description of this Structure. 
    The returned string should be python-compatible...
    '''
    s="%s # %s\n"%(prefix,repr(self) )
    for field,typ in self.getFields():
      attr=getattr(self,field)
      s+=self._attrToString(attr,field,typ,prefix)
    return s
    
  def _attrToString(self,attr,field,attrtype,prefix):
    s=''
    if isStructType(attrtype):
      s=prefix+'"%s": {\t%s%s},\n'%(field, attr.toString(prefix+'\t'),prefix )  
    elif isFunctionType(attrtype):
      s=prefix+'"%s": 0x%lx, #(FIELD NOT LOADED)\n'%(field, getaddress(attr) )   # only print address in target space
    elif isBasicTypeArray(attr): ## array of something else than int      
      #log.warning(field)
      s=prefix+'"%s": b%s,\n'%(field, repr(array2bytes(attr)) )  
      #s=prefix+'"%s" :['%(field)+','.join(["0x%lx"%(val) for val in attr ])+'],\n'
    elif isArrayType(attrtype): ## array of something else than int/byte
      # go through each elements, we hardly can make a array out of that...
      s=prefix+'"%s" :{'%(field)
      eltyp=type(attr[0])
      for i in range(0,len(attr)):
        s+=self._attrToString( attr[i], i, eltyp, '')
      s+='},\n'
      #s=prefix+'"%s" :['%(field)+','.join(["%s"%(val) for val in attr ])+'],\n'
    elif isPointerType(attrtype):
      if not bool(attr) :
        s=prefix+'"%s": 0x%lx,\n'%(field, getaddress(attr) )   # only print address/null
      elif isVoidPointerType(attrtype) :
        s=prefix+'"%s": 0x%lx, #Void pointer NOT LOADED\n'%(field, attr )   # only print address/null
      elif not is_address_local(attr) :
        s=prefix+'"%s": 0x%lx, #(FIELD NOT LOADED)\n'%(field, getaddress(attr) )   # only print address in target space
      else:
        # we can read the pointers contents # if isBasicType(attr.contents): ?  # if isArrayType(attr.contents): ?
        contents=attr.contents
        if type(self) == type(contents):
          s=prefix+'"%s": { #(0x%lx) -> %s\n%s},\n'%(field, getaddress(attr), type(attr.contents), prefix) # use struct printer
        elif isStructType(type(contents)): # do not enter in lists
          s=prefix+'"%s": { #(0x%lx) -> %s%s},\n'%(field, getaddress(attr), attr.contents.toString(prefix+'\t'),prefix) # use struct printer
        elif isPointerType(type(contents)):
          s=prefix+'"%s": { #(0x%lx) -> %s%s},\n'%(field, getaddress(attr), self._attrToString(attr.contents, None, None, prefix+'\t'), prefix ) # use struct printer
        else:
          s=prefix+'"%s": { #(0x%lx) -> %s\n%s},\n'%(field, getaddress(attr), attr.contents, prefix) # use struct printer
    elif isCStringPointer(attrtype):
      s=prefix+'"%s": "%s" , #(CString)\n'%(field, attr.string)  
    elif isBasicType(attrtype): # basic, ctypes.* !Structure/pointer % CFunctionPointer?
      s=prefix+'"%s": %s, \n'%(field, repr(attr) )  
    else: # wtf ?
      s=prefix+'"%s": %s, # Unknown/bug DEFAULT repr\n'%(field, repr(attr) )  
    return s

  def __str__(self):
    s=repr(self)+'\n'
    for field,attrtype in self.getFields():
      attr=getattr(self,field)
      if isStructType(attrtype):
        s+='%s (@0x%lx) : {\t%s}\n'%(field,ctypes.addressof(attr), attr )  
      elif isFunctionType(attrtype):
          s+='%s (@0x%lx) : 0x%lx (FIELD NOT LOADED)\n'%(field,ctypes.addressof(attr), getaddress(attr) )   # only print address in target space
      elif isBasicTypeArray(attr):
        try:
          s+='%s (@0x%lx) : %s\n'%(field,ctypes.addressof(attr), repr(array2bytes(attr)) )  
        except IndexError,e:
          log.error( 'error while reading %s %s'%(repr(attr),type(attr)) )
          
      elif isArrayType(attrtype): ## array of something else than int
        s+='%s (@0x%lx)  :['%(field, ctypes.addressof(attr),)+','.join(["%s"%(val) for val in attr ])+'],\n'
        continue
      elif isCStringPointer(attrtype):
        if not bool(attr) :
          s+='%s (@0x%lx) : 0x%lx\n'%(field,ctypes.addressof(attr), getaddress(attr) )   # only print address/null
        elif not is_address_local(attr) :
          s+='%s (@0x%lx) : 0x%lx (FIELD NOT LOADED)\n'%(field,ctypes.addressof(attr), getaddress(attr) )   # only print address in target space
        else:
          s+='%s (@0x%lx) : %s (CString) \n'%(field,ctypes.addressof(attr), attr.string)  
      elif isPointerType(attrtype) and not isVoidPointerType(attrtype): # bug with CString
        if not bool(attr) :
          s+='%s (@0x%lx) : 0x%lx\n'%(field, ctypes.addressof(attr),   getaddress(attr) )   # only print address/null
        elif not is_address_local(attr) :
          s+='%s (@0x%lx) : 0x%lx (FIELD NOT LOADED)\n'%(field, ctypes.addressof(attr), getaddress(attr) )   # only print address in target space
        elif type(self) == type(attr.contents): # do not recurse in lists
          s+='%s (@0x%lx) : (0x%lx) -> {%s}\n'%(field, ctypes.addressof(attr), getaddress(attr), repr(attr.contents) ) # use struct printer
        else:
          s+='%s (@0x%lx) : (0x%lx) -> {%s}\n'%(field, ctypes.addressof(attr), getaddress(attr), attr.contents) # use struct printer
      elif type(attr) is long or type(attr) is int:
        s+='%s : %s\n'%(field, hex(attr) )  
      else:
        s+='%s : %s\n'%(field, repr(attr) )  
    return s
    
  def toPyObject(self):
    ''' 
    Returns a Plain Old python object as a perfect copy of this ctypes object.
    array would be lists, pointers, inner structures, and circular 
    reference should be handled nicely.
    '''
    # get self class.
    #log.debug("%s %s %s_py"%(self.__class__.__module__, sys.modules[self.__class__.__module__], self.__class__.__name__) )
    my_class=getattr(sys.modules[self.__class__.__module__],"%s_py"%(self.__class__.__name__) )
    my_self=my_class()
    #keep ref
    if hasRef(my_class, ctypes.addressof(self) ):
      return getRef(my_class, ctypes.addressof(self) )
    # we are saving us in a partially resolved state, to keep from loops.
    keepRef(my_self, my_class, ctypes.addressof(self) )
    for field,typ in self.getFields():
      attr=getattr(self,field)
      member=self._attrToPyObject(attr,field,typ)
      setattr(my_self, field, member)
    # save the original type (me) and the field
    setattr(my_self, '_ctype_', type(self))
    return my_self
    
  def _attrToPyObject(self,attr,field,attrtype):
    if isStructType(attrtype):
      obj=attr.toPyObject()
    elif isBasicTypeArray(attr): ## array of basic types
      obj=array2bytes(attr)
    elif isArrayType(attrtype): ## array of something else than int/byte
      obj=[]
      eltyp=type(attr[0])
      for i in range(0,len(attr)):
        obj.append(self._attrToPyObject( attr[i], i, eltyp) )
    elif isPointerType(attrtype):
      if not bool(attr) :
        obj=(None,None)
      elif not is_address_local(attr) :
        obj=(None,getaddress(attr) )
      else:
        contents=attr.contents
        if isStructType(type(contents)) :
          attr_py_class = getattr(sys.modules[contents.__class__.__module__],"%s_py"%(contents.__class__.__name__) )
          cache = getRef(attr_py_class, getaddress(attr) )
          if cache:
            return cache
          obj=contents.toPyObject()
        elif isPointerType(type(contents)):
          obj=self._attrToPyObject(contents,None,None)
        else: # pointer vers autre chose, le repr() est le seul choix.
          #obj=repr(contents)
          obj=contents
    elif isCStringPointer(attrtype):
      obj=attr.string
    elif isFunctionType(attrtype):
      obj = repr(attr)
    elif isBasicType(attrtype) and isCTypes(attr):
      obj = attr.value
    else:
      obj = attr
    return obj

def json_encode_pyobj(obj):
  if hasattr(obj, '_ctype_'):
    return obj.__dict__
  elif type(obj).__name__ == 'int':
    log.warning('found an int')
    return str(obj)
  else:
    return obj
    
class pyObj(object):
  ''' 
  Base class for a plain old python object.
  all haystack/ctypes classes will be translated in this format before pickling.
  
  Operations :
    - toString(self, prefix):  print a nicely formatted data structure
        @param prefix: str to insert before each line (\t after that)
    - findCtypes(self) : checks if a ctypes is to be found somewhere is the object.
                      Useful to check if the object can be pickled.
  '''
  def toString(self, prefix='',maxDepth=10):
    if maxDepth < 0:
      return '#(- not printed by Excessive recursion - )'
    s='{\n'
    for attrname,typ in self.__dict__.items():
      attr = getattr(self, attrname)
      s += "%s%s: %s\n"%( prefix, attrname, self._attrToString(attr, attrname, typ, prefix+'\t', maxDepth=maxDepth-1) )
    s+='}'
    return s

  def _attrToString(self, attr, attrname, typ, prefix, maxDepth):
    s=''
    if type(attr) is tuple or type(attr) is list:
      for i in xrange(0,len(attr)):
        s += '%s,'%(self._attrToString(attr[i], i ,None, prefix+'\t', maxDepth) )
      s = "[%s],"%(s)
    elif not hasattr(attr,'__dict__'):
      s = '%s,'%( repr(attr) )
    elif  isinstance( attr , pyObj):
      s = '%s,'%( attr.toString(prefix,maxDepth) )
    else:
      s = '%s,'%(repr(attr) )
    return s

  def __len__(self):
    return self._len_
    
  def findCtypes(self):
    ret = False
    for attrname,attr in self.__dict__.items():
      # ignore _ctype_, it's a ctype class type, we know that.
      if attrname == '_ctype_' :
        continue
      typ = type(attr)
      attr = getattr(self, attrname)
      if self._attrFindCtypes(attr, attrname,typ ):
        log.warning('Found a ctypes in %s'%(attrname))
        ret = True
    return ret

  def _attrFindCtypes(self, attr, attrname, typ):
    ret = False
    if hasattr(attr, '_ctype_'): # a pyobj
      return attr.findCtypes()
    elif type(attr) is tuple or type(attr) is list:
      for el in attr:
        if self._attrFindCtypes(el, 'element', None):
          log.warning('Found a ctypes in array/tuple')
          return True
    elif isCTypes(attr):
      log.warning('Found a ctypes in self  %s'%(attr))
      return True
    else: # int, long, str ...
      ret = False
    return ret

  def __iter__(self):
    ''' iterate on a instance's type's _fields_ members following the original type field order '''
    for k,typ in self._ctype_.getFields():
      v = getattr(self,k)
      yield (k,v,typ)
    pass

def findCtypesInPyObj(obj):
  ''' check function to help in unpickling errors correction '''
  ret = False
  if hasattr(obj, 'findCtypes'):
    if obj.findCtypes():
      log.warning('Found a ctypes in array/tuple')
      return True
  elif type(obj) is tuple or type(obj) is list:
    for el in obj:
      if findCtypesInPyObj(el):
        log.warning('Found a ctypes in array/tuple')
        return True
  elif isCTypes(obj):
    return True
  return False
      
import inspect,sys

def copyGeneratedClasses(src, dst):
  ''' 
    Copies the members of a generated module into a classic module.
    Name convention : 
    generated: ctypes_libraryname_generated.py
    classic  : ctypes_libraryname.py
    
  @param me : dst module
  @param src : src module, generated
  '''
  __root_module_name,__dot,__module_name = dst.__name__.rpartition('.')
  _loaded=0
  _registered=0
  for (name, klass) in inspect.getmembers(src, inspect.isclass):
    if type(klass) == type(ctypes.Structure):
      if klass.__module__.endswith('%s_generated'%(__module_name) ) :
        setattr(dst, name, klass)
        _loaded+=1
    else:
      #log.debug("%s - %s"%(name, klass))
      pass
  log.debug('loaded %d C structs from %s structs'%( _loaded, src.__name__))
  log.debug('registered %d Pointers types'%( _registered))
  log.debug('There is %d members in %s'%(len(src.__dict__), src.__name__))
  return 


def createPOPOClasses( targetmodule ):
  ''' Load all model classes and create a similar non-ctypes Python class  
    thoses will be used to translate non pickable ctypes into POPOs.
  '''
  _created=0
  for klass,typ in inspect.getmembers(targetmodule, inspect.isclass):
    if typ.__module__.startswith(targetmodule.__name__):
      kpy = type('%s.%s_py'%(targetmodule.__name__, klass),( pyObj ,),{})
      # add the structure size to the class
      if type(typ) == type(LoadableMembers) or type(typ) == type( ctypes.Union) :
        setattr(kpy, '_len_',ctypes.sizeof(typ) )
      else:
        setattr(kpy, '_len_', None )
      # we have to keep a local (model) ref because the class is being created here.
      # and we have a targetmodule ref. because it's asked.
      # and another ref on the real module for the basic type, because, that is probably were it's gonna be used.
      setattr(sys.modules[__name__], '%s.%s_py'%(targetmodule.__name__, klass), kpy )
      #setattr(sys.modules[__name__], '%s_py'%(klass), kpy )
      setattr(targetmodule, '%s_py'%(klass), kpy )
      _created+=1
      if typ.__module__ != targetmodule.__name__: # copy also to generated
        setattr(sys.modules[typ.__module__], '%s_py'%(klass), kpy )
        #log.debug("Created %s_py"%klass)
  log.debug('created %d POPO types'%( _created))
  return

def registerModule( targetmodule ):
  ''' 
  Registers a ctypes module. To be run by target module.
  
  All members in this module will be registered, against their pointer types,
  in a lookup table.
  
  Creates POPO's to be able to unpickle ctypes.
  '''
  if targetmodule in registeredModules():
    log.warning('Module %s already registered. Skipping.'%(targetmodule))
    return
  _registered = 0
  for klass,typ in inspect.getmembers(targetmodule, inspect.isclass):
    if typ.__module__.startswith(targetmodule.__name__) and issubclass(typ, ctypes.Structure):
      register( typ )
      _registered += 1
  # create POPO's
  createPOPOClasses( targetmodule )
  __book.addModule(targetmodule)
  log.debug('registered %d types'%( _registered))
  log.debug('regisered %d module total'%(len(__book.getModules())))
  return

def isRegistered(cls):
  #return cls in sys.modules[__name__].__dict__.values()
  return __book.isRegisteredType(cls)

# create local POPO ( lodableMembers )
#createPOPOClasses(sys.modules[__name__] )
LoadableMembers_py = type('%s.%s_py'%(__name__, LoadableMembers),( pyObj ,),{})
# register LoadableMembers 
register(LoadableMembers)


# replace c_char_p - it can handle memory parsing without reading it 
if ctypes.c_char_p.__name__ == 'c_char_p':
  ctypes.c_char_p = CString

# switch class - we need our methods on ctypes.Structures for generated classes to work  
if ctypes.Structure.__name__ == 'Structure':
  ctypes.Structure = LoadableMembers

