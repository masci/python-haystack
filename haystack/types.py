import sys

__PROXIES = {}

def reset_ctypes():
    """Reset sys.module to import the host ctypes module."""
    # remove all refs to the ctypes modules or proxies
    if 'ctypes' in sys.modules:
        del sys.modules['ctypes']
    # import the real one
    import ctypes
    return ctypes

def load_ctypes_default():
    """Load sys.module with a default host-mimicking ctypes module proxy."""
    reset_ctypes()
    import ctypes
    # get the hosts' types
    longsize = ctypes.sizeof(ctypes.c_long)
    pointersize = ctypes.sizeof(ctypes.c_void_p)
    longdoublesize = ctypes.sizeof(ctypes.c_longdouble)
    return reload_ctypes(longsize, pointersize, longdoublesize)


def reload_ctypes(longsize, pointersize, longdoublesize):
    """Load sys.modle with a tuned ctypes module proxy."""
    if (longsize, pointersize, longdoublesize) in __PROXIES:
        instance = __PROXIES[(longsize, pointersize, longdoublesize)]
        set_ctypes(instance)
        return instance
    instance = CTypesProxy(longsize, pointersize, longdoublesize)
    __PROXIES[(longsize, pointersize, longdoublesize)] = instance
    return instance

def set_ctypes(ctypesproxy):
    """Load Change the global ctypes module to a specific proxy instance"""
    if not isinstance(ctypesproxy, CTypesProxy):
        raise TypeError('CTypesProxy instance expected.')
    sys.modules['ctypes'] = ctypesproxy
    return sys.modules['ctypes']

def check_arg_is_type(func):
    def check_arg(self, objtype):
        if not isinstance(objtype, type):
            return False
        return func(self, objtype)
    check_arg.__name__ = func.__name__
    check_arg.__doc__ = func.__doc__
    check_arg.__dict__.update(func.__dict__)
    return check_arg


class CTypesProxy(object):
    """# TODO: set types in config.Types
    # ctypeslib generate python code based on config.Types.*
    # never import ctypes, but proxy always through instance of config.
    # flow:
    # a) init config with size/etc.
    # b) init model instance with config instance
    # c) create structure & Union proxied in model instance
    # d) refer to config through dynamically generated Structure/Union classes.

    # sys.modules['ctypes'] = proxymodule/instance

    By default do not load this in model
    """
    def __init__(self, longsize, pointersize, longdoublesize):
        """Proxies 'the real' ctypes."""
        self.proxy = True
        self.__longsize = longsize
        self.__pointersize = pointersize
        self.__longdoublesize = longdoublesize
        # remove all refs to the ctypes modules or proxies
        reset_ctypes()
        # import the real one
        import ctypes
        self.__real_ctypes = ctypes
        if hasattr(ctypes,'proxy'):
            raise RuntimeError('base ctype should not be a proxy')
        # copy every members
        for name in dir(ctypes):
            if not name.startswith('__'):
                setattr(self, name, getattr(ctypes, name))
        del ctypes
        # replace it.
        sys.modules['ctypes'] = self
        self.__init_types()
        pass        

    def __init_types(self):
        self.__set_void()
        self.__set_int128()
        self.__set_long()
        self.__set_float()
        self.__set_pointer()
        self.__set_records()
        self.__set_utils_types()
        return

    def __set_void(self):
        self.void = None
        return
        
    def __set_int128(self):
        self.c_int128 = self.__real_ctypes.c_ubyte*16
        self.c_uint128 = self.c_int128
        return

    def __set_long(self):
        # use host type if target is the same
        if self.sizeof(self.__real_ctypes.c_long) == self.__longsize:
            return
        if self.__longsize == 4:
            self.c_long = self.__real_ctypes.c_int32
            self.c_ulong = self.__real_ctypes.c_uint32
        elif self.__longsize == 8:
            self.c_long = self.__real_ctypes.c_int64
            self.c_ulong = self.__real_ctypes.c_uint64
        else:
            raise NotImplementedError('long size of %d is not handled'%(self.__longsize))

    def __set_float(self):
        # use host type if target is the same
        if self.sizeof(self.__real_ctypes.c_longdouble) == self.__longdoublesize:
            return
        #self.c_longdouble = self.c_ubyte*self.__longdoublesize
        #self.c_longdouble.__name__ = 'c_longdouble'
        SIZE = self.__longdoublesize
        class c_longdouble(self.__real_ctypes.Union):
            """This is our own implementation of a longdouble.
            It could be anywhere from 64(win) to 80 bits, stored as 8, 12, 
            or 16 bytes."""
            _packed_ = True
            _fields_ = [
                ("physical", self.c_ubyte*SIZE )
            ]
            _type_ = 'g' # fake it
        self.c_longdouble = c_longdouble
        return

    def __set_pointer(self):
        # TODO: c_char_p ?
        # if host pointersize is same as target, keep ctypes pointer function.
        if self.sizeof(self.__real_ctypes.c_void_p) == self.__pointersize:
            return
        # get the replacement type.
        if self.__pointersize == 4:
            replacement_type = self.__real_ctypes.c_uint32
            replacement_type_char = self.__real_ctypes.c_uint32._type_
        elif self.__pointersize == 8:
            replacement_type = self.__real_ctypes.c_uint64
            replacement_type_char = self.__real_ctypes.c_uint64._type_
        else:
            raise NotImplementedError('pointer size of %d is not handled'%(self.__pointersize))
        POINTERSIZE = self.__pointersize
        # required to access _ctypes
        import _ctypes
        # Emulate a pointer class using the approriate c_int32/c_int64 type
        # The new class should have :
        # ['__module__', 'from_param', '_type_', '__dict__', '__weakref__', '__doc__']
        def POINTER_T(pointee):
            # a pointer should have the same length as LONG
            fake_ptr_base_type = replacement_type
            # specific case for c_void_p
            if pointee is None: # VOID pointer type. c_void_p.
                pointee = type(None) # ctypes.c_void_p # ctypes.c_ulong
                clsname = 'c_void'
            else:
                clsname = pointee.__name__
            # make template
            class _T(_ctypes._SimpleCData,):
                _type_ = replacement_type_char
                _subtype_ = pointee
                def _sub_addr_(self):
                    return self.value
                def __repr__(self):
                    return '%s(%d)'%(clsname, self.value)
                def contents(self):
                    raise TypeError('This is not a ctypes pointer.')
                def __init__(self, **args):
                    raise TypeError('This is not a ctypes pointer. It is not instanciable.')
            _class = type('LP_%d_%s'%(POINTERSIZE, clsname), (_T,),{}) 
            return _class
        self.POINTER = POINTER_T
        self.c_void_p = self.POINTER(None)
        self.c_char_p = self.POINTER(self.c_char)
        self.c_wchar_p = self.POINTER(self.c_wchar)
        return

    def __set_records(self):
        """Replaces ctypes.Structure and ctypes.Union with their LoadableMembers
        counterparts. Add a CString type.
        MAYBE FIXME: These root types will only be valid when the ctypes record is 
        used with the adequate CTypesProxy.
        """
        class CString(self.__real_ctypes.Union):
            """
            This is our own implementation of a string for ctypes.
            ctypes.c_char_p can not be used for memory parsing, as it tries to load 
            the string itself without checking for pointer validation.

            it's basically a Union of a string and a pointer.
            """
            _fields_=[
                #("string", self.__real_ctypes.original_c_char_p),
                ("string", self.c_char_p),
                ("ptr", self.POINTER(self.c_ubyte) )
            ]
            _type_ = 's' # fake it
            def toString(self):
                if not bool(self.ptr):
                    return "<NULLPTR>"
                if hasRef(CString, getaddress(self.ptr)):
                    return getRef(CString, getaddress(self.ptr) )
                log.debug('This CString was not in cache - calling toString was not a good idea')
                return self.string
                pass
        # and there we have it. We can load basicmodel
        self.CString = CString
        
        ## change LoadableMembers structure given the loaded plugins
        import basicmodel
        if True:
            import listmodel
            heritance = tuple([listmodel.ListModel,basicmodel.LoadableMembers])
        else:
            heritance = tuple([basicmodel.LoadableMembers])
        self.LoadableMembers = type('LoadableMembers', heritance, {})

        class LoadableMembersUnion(self.__real_ctypes.Union, self.LoadableMembers):
            pass
        class LoadableMembersStructure(self.__real_ctypes.Structure, self.LoadableMembers):
            pass
        # create local POPO ( lodableMembers )
        #createPOPOClasses(sys.modules[__name__] )
        self.LoadableMembersStructure_py = type('%s.%s_py'%(__name__, LoadableMembersStructure),( basicmodel.pyObj ,),{})
        self.LoadableMembersUnion_py = type('%s.%s_py'%(__name__, LoadableMembersUnion),( basicmodel.pyObj ,),{})
        # register LoadableMembers 

        # we need model to be initialised.
        self.Structure = LoadableMembersStructure
        self.Union = LoadableMembersUnion
        return

    def __set_utils_types(self):
        """Creates some types to compare to"""
        self.__arrayt = type(self.c_byte*1)
        self.__cfuncptrt = type(type(self.memmove))
        class _p(self.Structure):
            pass
        self.__ptrt = type(self.POINTER(_p))
        self.__basic_types_name = {
            'c_bool': '?',
            'c_char': 'c',
            'c_byte': 'b',
            'c_ubyte': 'B',
            'c_short': 'h',
            'c_ushort': 'H',
            'c_int': 'i', #c_int is c_long
            'c_uint': 'I',
            'int': 'i', 
            'c_long': 'l', #c_int is c_long
            'c_ulong': 'L',
            'long': 'q', 
            'c_longlong': 'q',
            'c_ulonglong': 'Q',
            'c_float': 'f', 
            'c_double': 'd', 
            'c_longdouble': 'g', 
            'c_char_p': 's',
            'c_void_p': 'P',
            'c_void': 'P', ## void in array is void_p ##DEBUG
            }
        # we need to account for the possible changes in c_longdouble
        self.__basic_types = set([getattr(self,k) for k in self.__basic_types_name.keys() if hasattr(self,k)])
        return
    

    #import sys
    #from inspect import getmembers, isclass
    #self = sys.modules[__name__]
    def _p_type(s):
        """CHECKME: Something about self reference in structure fields in ctypeslib"""
        return dict(getmembers(self, isclass))[s]

    def get_real_ctypes_member(self, typename):
        return getattr(self.__real_ctypes, typename)

    ######## migration from utils.
    def is_ctypes_instance(self, obj):
        """Checks if an object is a ctypes type object"""
        # FIXME. is it used for loadablemembers detection or for ctypes VS POPO
        return issubclass(type(obj), self.get_real_ctypes_member('Structure'))

    def is_array_to_basic_instance(self, obj):
        """Checks if an object is a array of basic types.
        It checks the type of the first element.
        The array should not be null :).
        """
        if not hasattr(obj, '_type_'):
            return False
        if self.is_array_type(type(obj)):
            if len(obj) == 0:
                return False # no len is no BasicType
            if self.is_pointer_type(obj._type_):
                return False
            if self.is_basic_type(obj._type_):
                return True
        return False

    @check_arg_is_type
    def is_array_type(self, objtype):
        """Checks if an object is a ctype array."""
        return self.__arrayt == type(objtype)

    @check_arg_is_type
    def is_basic_type(self, objtype):
        """Checks if an object is a ctypes basic type, or a python basic type."""
        if not hasattr(objtype, '_type_'):
            return False
        if objtype in [self.c_char_p, self.c_void_p, self.CString]:
            return False
        return objtype in self.__basic_types

    @check_arg_is_type
    def is_cstring_type(self, objtype):
        """Checks if an object is our CString."""
        return issubclass(objtype, self.CString) 

    @check_arg_is_type
    def is_function_type(self, objtype):
        """Checks if an object is a function pointer."""
        return self.__cfuncptrt == type(objtype)

    @check_arg_is_type
    def is_pointer_type(self, objtype):
        """ Checks if an object is a ctypes pointer.m CTypesPointer or CSimpleTypePointer"""
        if hasattr(objtype, '_subtype_'):
            return True
        if hasattr(objtype, '_type_'):
            # all basic types, pointers and array have a _type_
            return not (self.is_basic_type(objtype) or
                        self.is_array_type(objtype) ) # kinda true. I guess.
        # remaining case
        return (self.is_function_type(objtype))

    @check_arg_is_type
    def is_pointer_to_basic_type(self, objtype):
        """Checks if an object is a pointer to a BasicType"""
        return hasattr(objtype, '_type_') and self.is_basic_type(objtype._type_)

    @check_arg_is_type
    def is_pointer_to_struct_type(self, objtype):
        """Checks if an object is a pointer to a Structure"""
        return hasattr(objtype, '_type_') and self.is_struct_type(objtype._type_)

    @check_arg_is_type
    def is_pointer_to_union_type(self, objtype):
        """Checks if an object is a pointer to a Union"""
        return hasattr(objtype, '_type_') and self.is_union_type(objtype._type_)

    @check_arg_is_type
    def is_pointer_to_void_type(self, objtype):
        """FIXME Checks if an object is a ctypes pointer.m CTypesPointer or CSimpleTypePointer"""
        # FIXME: DOCME what is that _subtype_ case
        if hasattr(objtype, '_subtype_'):
            if objtype._subtype_ == type(None):
                return True 
        # FIXME: DOCME what are these cases ? not auto-loading ?
        # self.POINTER(None) is required, because sometimes, c_void_p != c_void_p :)
        return objtype in [self.c_char_p, self.c_wchar_p, self.c_void_p, self.POINTER(None)]

    @check_arg_is_type
    def is_struct_type(self, objtype):
        """ Checks if an object is a ctypes Structure."""
        return issubclass(objtype, self.get_real_ctypes_member('Structure'))

    @check_arg_is_type
    def is_union_type(self, objtype):
        """ Checks if an object is a ctypes Union."""
        # force ignore the longdouble construct
        if objtype == self.c_longdouble:
            return False
        # force ignore the CString construct
        if objtype == self.CString:
            return False
        return issubclass(objtype, self.get_real_ctypes_member('Union'))

      

    def __str__(self):
        return "<haystack.types.CTypesProxy-%d:%d:%d-%x>"%(self.__longsize,self.__pointersize,self.__longdoublesize,id(self))

    # TODO implement haystack.utils.bytestr_fmt here




