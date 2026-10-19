"""Extract discovery URLs from the news/featured-content pages of supplied PDFs.

Requires pypdf, available in the Codex bundled Python environment.
This reads annotations, not article text or OCR. It excludes contact-directory URLs.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from pypdf import PdfReader

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--advent',required=True,type=Path)
parser.add_argument('--hca',required=True,type=Path)
args=parser.parse_args()
links=[]
for path,system,start,end in [(args.advent,'adventhealth',5,25),(args.hca,'hca',5,16)]:
    reader=PdfReader(path)
    if len(reader.pages)<end:
        raise ValueError(f'{path.name}: expected profile pagination has changed.')
    seen=set()
    for page_no in range(start,end+1):
        for ref in reader.pages[page_no-1].get('/Annots',[]):
            action=ref.get_object().get('/A',{})
            url=str(action.get('/URI',''))
            parsed=urlparse(url)
            if parsed.scheme!='https' or not parsed.hostname or url in seen:
                continue
            if parsed.hostname.endswith('idndirectory.com') and parsed.path.startswith('/contacts/'):
                continue
            seen.add(url)
            links.append(dict(system=system,url=url,profile=path.name,page=page_no))
output=Path(__file__).resolve().parents[1]/'data'/'source_inventory.json'
output.write_text(json.dumps({'note':'PDF news/featured-content hyperlinks; contact-directory links excluded. Discovery candidates only; not verified for access, relevance, or collection permission.','links':links},indent=2),encoding='utf-8')
print(f'Saved {len(links)} candidate links.')
