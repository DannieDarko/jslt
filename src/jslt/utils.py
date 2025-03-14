from typing import Union

def deep_copy(obj: Union[dict, list]):
  copy_obj={'root': type(obj)()}
  cur_itm=None
  copy_stack=[(obj, copy_obj, 'root')]
  while copy_stack:
    parent=cur_itm
    cur_itm, cur_obj, cur_key=copy_stack.pop(0)
    if isinstance(cur_itm, list):
      cur_obj[cur_key]=[None for i in range(len(cur_itm))]
      copy_stack+=[(v, cur_obj[cur_key], i) for i, v in enumerate(cur_itm)]
    elif isinstance(cur_itm, dict):
      cur_obj[cur_key]={}
      for k, v in cur_itm.items():
        copy_stack.append((v, cur_obj[cur_key], k))
    else:
      cur_obj[cur_key]=cur_itm
  return copy_obj['root']