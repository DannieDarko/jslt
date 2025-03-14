import jmespath
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Self, Union
from .utils import deep_copy

class JSON(ABC):
    @abstractmethod
    def __iter__(self):
        pass
    @abstractmethod
    def copy(self):
        pass
    @abstractmethod
    def to_json(self):
        pass
    @abstractmethod
    def current(self):
        pass

class JSONList(JSON):
    def __init__(self, children: list[JSON]=[]):
        logger=logging.getLogger(self.__class__.__name__)
        object.__setattr__(self, '__logger__', logger)
        object.__setattr__(self, '__children__', children)

    def append(self, child: JSON):
        children=object.__getattribute__(self, '__children__')
        children.append(child)

    def to_json(self):
        return [c.to_json() if isinstance(c, JSON) else c for c in self.__children__]

    def copy(self):
        return type(self)(c.copy() for c in self.__children__)
    
    def first(self):
        return self.__children__[0] if self.__children__ else JSONDict({})
    
    def last(self):
        return self.__children__[-1] if self.__children__ else JSONDict({})
    
    def current(self):
        return self

    def __str__(self):
        return f"[{', '.join([str(c) for c in self.__children__])}]"

    def __iter__(self):
        return iter(self.__children__)

    def __getitem__(self, key: str):
        children=object.__getattribute__(self, '__children__')
        if isinstance(key, int):
            return children[key]
        match=re.match(r'^([^<>=!]+)(={1,2}|!=|<|>|<=|>=)([^<>=!]+)$', key)
        found=[]
        if match:
            comp='==' if match.group(2)=='=' else match.group(2)
            for child in children:
                if isinstance(child, dict):
                    child=JSONDict(child)
                if not isinstance(child, JSONDict):
                    continue
                term1=str(child.jpath(match.group(1)))
                term2=str(child.jpath(match.group(3)))
                if not re.match(r'^[0-9]*(\.[0-9]+)?$', term1):
                    term1=f"'{term1}'"
                if not re.match(r'^[0-9]*(\.[0-9]+)?$', term2):
                    term2=f"'{term2}'"
                self.__logger__.info(f'Filter: {term1} {comp} {term2}')
                if eval(f'{term1}{comp}{term2}'):
                    found.append(child)
        return JSONList(found)

class JSONDict(JSON):
    def __init__(self, _json: dict={}, _value=None):
        object.__setattr__(self, '__logger__', logging.getLogger(self.__class__.__name__))
        object.__setattr__(self, '__value__', _value)
        object.__setattr__(self, '__json__', deep_copy(_json))

    def __getitem__(self, key: str):
        match=re.match(r'^([^<>=!]+)(={1,2}|!=|<|>|<=|>=)([^<>=!]+)$', key)
        found=type(self)()
        if match:
            comp='==' if match.group(2)=='=' else match.group(2)
            term1=str(self.jpath(match.group(1)))
            term2=str(self.jpath(match.group(3)))
            if not re.match(r'^[0-9]*(\.[0-9]+)?$', term1):
                term1=f"'{term1}'"
            if not re.match(r'^[0-9]*(\.[0-9]+)?$', term2):
                term2=f"'{term2}'"
            self.__logger__.info(f'Filter: {term1} {comp} {term2})')
            if eval(f'{term1}{comp}{term2}'):
                found=self
        return found

    def __getattr__(self, name: str):
        if name[:2]=='__':
            return object.__getattribute__(self, name)
        attr=self.__json__.get(name, {})
        if isinstance(attr, dict):
            return type(self)(_json=attr)
        elif isinstance(attr, list):
            return JSONList([type(self)(_json=i) if isinstance(i, dict) else JSONList([type(self)(_json=e) if isinstance(e, dict) else type(self)(_value=e) for e in i]) if isinstance(i, list) else type(self)(_value=i) for i in attr])
        return type(self)(_value=attr)

    def __setattr__(self, attr: str, val):
        if attr[:2]=='__':
            object.__setattr__(self, attr, val)
        self.__json__[attr]=val

    def __hasattr__(self, attr: str):
        print('hasattr', attr)

    def __iter__(self):
        return iter(self.__json__)

    def __str__(self):
        if self.__value__:
            return str(self.__value__)
        else:
            return str(self.__json__)

    def __float__(self):
        return 0.1

    def to_json(self):
        return self.__value__ or dict(self.__json__.copy())

    def keys(self):
        return self.__json__.keys()

    def items(self):
        return self.__json__.items()

    def values(self):
        return self.__json__.values()

    def get(self, name: str, default={}):
        attr=self.__json__.get(name, default)
        if isinstance(attr, list):
            return JSONList(attr)
        elif isinstance(attr, dict):
            return type(self)(_json=attr)
        return type(self)(_value=attr)
    
    def copy(self):
        if self.__value__:
            return type(self)(_value=self.__value__)
        return type(self)(_json=deep_copy(self.__json__))

    def current(self):
        return self

    def text(self):
        return str(self)

    def number(self):
        return float(self.__value__)

    def jpath(self, path: str, default: Union[None, object]=None, vars: dict={}):
        res=None
        try:
            path=path.replace('$', '__vars__')
            # res=eval(path, {'__builtins__': {'str': str, 'int': int, 'float': float, 'abs': abs, 'round': round, 'copy': self.copy, 'text': self.text, 'number': self.number, 'current': self.current}}, {**{k: self.get(k) for k in self.keys()}, **{f'__vars__{k}': v for k, v in vars.items()}})
            res=jmespath.search(path, self.__json__)
        except Exception as e:
            self.__logger__.error(f'Error in path {path}: {e}')
            pass
        return res if res is not None else default
    
class JSLT:
  def __init__(self, jslt: Union[list, dict]):
    self.__logger__=logging.getLogger(self.__class__.__name__)
    self.jslt=deep_copy(jslt)
    self.vars={}
    self.context=None
    self.parentContext=None

  def jsl_var(self, variable: dict):
    var_name=variable.get('name') or (self.parentContext and self.parentContext.cur_key)
    if not var_name:
        self.__logger__.error('Variable name is not set')
        return
    value=variable.get('value')
    if 'path' in variable:
        res=self.jsl_path(variable['path'])
        if res is not None:
            value=res
    self.__logger__.info(f'Variable: {var_name} = {value}')
    self.vars[var_name]=value

  def jsl_path(self, path, default=None):
    self.__logger__.info(f'Path: {path} ({default})')
    res=self.context.jpath(path, default, vars=self.vars)
    if not res:
        return default
    return JSONList(res) if isinstance(res, list) else JSONDict(_json=res) if isinstance(res, dict) else JSONDict(_value=res)

  def jsl_if(self, conditional):
    match=re.match(r'^([^<>=!]+)(={1,2}|!=|<|>|<=|>=)([^<>=!]+)$', conditional.get('test'))
    if match:
      comp='==' if match.group(2)=='=' else match.group(2)
      term1=str(self.jsl_path(match.group(1)))
      term2=str(self.jsl_path(match.group(3)))
      if not re.match(r'^[0-9]*(\.[0-9]+)?$', term1):
        term1=f"'{term1}'"
      if not re.match(r'^[0-9]*(\.[0-9]+)?$', term2):
        term2=f"'{term2}'"
      self.__logger__.info((term1, comp, term2))
      if eval(f'{term1}{comp}{term2}'):
        return conditional.get('then')
    return conditional.get('else')

  def jsl_each(self, each_condition):
    context=self.jsl_path(each_condition.get('path', []))
    jslt=JSLT(each_condition.get('template', {}))
    jslt.vars['root']=self.jslt
    if context is None:
        return None
    elif not isinstance(context, JSONList):
      return jslt.transform(context)
    return [jslt.transform(item) for item in context]

  def transform(self, json):
    class StackItem:
      def __init__(self, cur_itm: object, cur_obj: Union[list, dict], cur_key: Union[int, str], parent: Union[Self, None]=None):
        self.cur_itm=cur_itm
        self.cur_obj=cur_obj
        self.cur_key=cur_key
        self.parent=parent

    self.context=JSONDict(json) if not isinstance(json, JSON) else json
    self.parentContext=None
    copy_obj={'root': type(self.jslt)()}
    cur_itm=None
    stack_item=None
    copy_stack=[StackItem(self.jslt, copy_obj, 'root')]
    while copy_stack:
      stack_item=copy_stack.pop(0)
      parent=stack_item.parent
      self.parentContext=parent
      cur_itm=stack_item.cur_itm
      cur_obj=stack_item.cur_obj
      cur_key=stack_item.cur_key
      if isinstance(cur_key, str) and cur_key[:4]=='jsl:':
        jsl_function_name='jsl_'+cur_key[4:]
        jsl_function=None
        if hasattr(self, jsl_function_name):
          jsl_function=getattr(self, jsl_function_name)
        if jsl_function and callable(jsl_function):
          if not isinstance(cur_itm, list):
            cur_itm=[cur_itm]
          res=jsl_function(*cur_itm)
          if isinstance(res, JSON):
            res=res.to_json()
          if res is None:
            del parent.cur_obj[parent.cur_key]
          else:
            copy_stack.append(StackItem(res, parent.cur_obj, parent.cur_key))
        else:
          self.__logger__.error(f'No such function: {jsl_function_name}')
      elif isinstance(cur_itm, list):
        cur_obj[cur_key]=[None for i in range(len(cur_itm))]
        copy_stack+=[StackItem(v, cur_obj[cur_key], i, stack_item) for i, v in enumerate(cur_itm)]
      elif isinstance(cur_itm, dict):
        cur_obj[cur_key]={}
        for k, v in cur_itm.items():
          copy_stack.append(StackItem(v, cur_obj[cur_key], k, stack_item))
      else:
        cur_obj[cur_key]=cur_itm
    return copy_obj['root']