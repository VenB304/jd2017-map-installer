from pathlib import Path
path = Path(r'c:\Github\jd2017-map-installer\jd2017_installer\parsers\normalizer.py')
text = path.read_text(encoding='utf-8')
# Remove null bytes if any
text = text.replace('\x00', '')
# Remove the bad echo if it exists
text = text.replace('def normalize(*args, **kwargs): return None\n', '')
text = text.replace('def normalize(*args, **kwargs): return None', '')

stub = '\n\ndef normalize(*args, **kwargs): return None\n'
path.write_text(text + stub, encoding='utf-8')
print("normalizer.py fixed")
