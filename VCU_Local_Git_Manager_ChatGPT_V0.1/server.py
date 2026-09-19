import json, hashlib, difflib, subprocess, shutil, datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

BASE=Path(__file__).resolve().parent
CONFIG=BASE/"config.json"
LOG=BASE/"activity.json"
BACKUPS=BASE/"backups"
REPORTS=BASE/"reports"
DEFAULT={"local_path":"","repo":"","branch":"main","remote_path":"/","port":8765,"theme":"light","auto_backup":True,"v1":"V1","v2":"V2","notes":""}

def load_json(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return default

def save_json(p,d):
    p.write_text(json.dumps(d,indent=2),encoding="utf-8")

DATA=DEFAULT|load_json(CONFIG,{})
if not CONFIG.exists(): save_json(CONFIG,DATA)
if not LOG.exists(): save_json(LOG,[])

def activity(op,notes="",extra=None):
    a=load_json(LOG,[])
    a.insert(0,{"time":datetime.datetime.now().astimezone().isoformat(),"operation":op,"notes":notes,**(extra or {})})
    save_json(LOG,a[:500])

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b): h.update(b)
    return h.hexdigest()

def is_text(p):
    try:
        b=p.read_bytes()
        if b"\0" in b[:8192]: return False
        b.decode("utf-8")
        return True
    except Exception: return False

def rel_files(base):
    base=Path(base); out={}
    for p in base.rglob("*"):
        if p.is_file() and not any(x in p.parts for x in [".git","backups","reports"]):
            out[str(p.relative_to(base)).replace("\\","/")]=p
    return out

def compare_dirs(a,b):
    A,B=rel_files(a),rel_files(b); result=[]
    for n in sorted(set(A)|set(B)):
        pa,pb=A.get(n),B.get(n)
        if not pa:
            result.append({"file":n,"status":"ADDED","a_size":0,"b_size":pb.stat().st_size,"a_lines":0,"b_lines":len(pb.read_text(encoding="utf-8",errors="replace").splitlines()) if is_text(pb) else 0})
            continue
        if not pb:
            result.append({"file":n,"status":"DELETED","a_size":pa.stat().st_size,"b_size":0,"a_lines":len(pa.read_text(encoding="utf-8",errors="replace").splitlines()) if is_text(pa) else 0,"b_lines":0})
            continue
        same=sha(pa)==sha(pb)
        item={"file":n,"status":"UNCHANGED" if same else "MODIFIED","a_size":pa.stat().st_size,"b_size":pb.stat().st_size,"a_hash":sha(pa),"b_hash":sha(pb)}
        if is_text(pa) and is_text(pb):
            x=pa.read_text(encoding="utf-8",errors="replace").splitlines()
            y=pb.read_text(encoding="utf-8",errors="replace").splitlines()
            item["a_lines"],item["b_lines"]=len(x),len(y)
            if not same:
                item["diff"]="\n".join(difflib.unified_diff(x,y,fromfile="V1/"+n,tofile="V2/"+n,lineterm=""))
        result.append(item)
    return result

def git(args,cwd):
    p=subprocess.run(["git"]+args,cwd=cwd,text=True,capture_output=True)
    return {"code":p.returncode,"stdout":p.stdout,"stderr":p.stderr}

class Handler(SimpleHTTPRequestHandler):
    def send_json(self,code,obj):
        data=json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        u=urlparse(self.path).path
        if u=="/api/config": self.send_json(200,DATA); return
        if u=="/api/activity": self.send_json(200,load_json(LOG,[])); return
        if u=="/": self.path="/static/index.html"
        return super().do_GET()

    def do_POST(self):
        n=int(self.headers.get("Content-Length",0))
        try: body=json.loads(self.rfile.read(n) or b"{}")
        except Exception: self.send_json(400,{"error":"Invalid JSON"}); return
        u=urlparse(self.path).path

        if u=="/api/config":
            DATA.update(body); save_json(CONFIG,DATA); self.send_json(200,DATA); return

        if u=="/api/compare":
            a=body.get("a") or DATA["local_path"]; b=body.get("b")
            if not a or not b or not Path(a).is_dir() or not Path(b).is_dir():
                self.send_json(400,{"error":"Both local comparison folders must exist on this PC."}); return
            r=compare_dirs(a,b)
            summary={k:sum(x["status"]==k for x in r) for k in ["UNCHANGED","MODIFIED","ADDED","DELETED"]}
            self.send_json(200,{"files":r,"summary":summary}); return

        if u=="/api/report":
            REPORTS.mkdir(exist_ok=True)
            name=body.get("name","DIFFERENCE_V1_TO_V2.txt")
            p=REPORTS/name
            lines=["VCU PROJECT REVISION DIFFERENCE","="*70,"",
                   "FROM: "+body.get("v1","V1"),"TO: "+body.get("v2","V2"),
                   "BRANCH: "+body.get("branch",DATA["branch"]),
                   "GENERATED: "+datetime.datetime.now().astimezone().isoformat(),"",
                   "USER NOTES:",body.get("notes",""),"",
                   "SUMMARY","="*70]
            for k,v in body.get("summary",{}).items(): lines.append(f"{k}: {v}")
            lines+=["","FILE DIFFERENCES","="*70]
            for x in body.get("files",[]):
                lines += [f"\nFILE: {x['file']}",f"STATUS: {x['status']}",
                          f"SIZE: {x.get('a_size',0)} -> {x.get('b_size',0)} bytes",
                          f"LINES: {x.get('a_lines',0)} -> {x.get('b_lines',0)}"]
                if x.get("a_hash"): lines += [f"V1 SHA256: {x['a_hash']}",f"V2 SHA256: {x['b_hash']}"]
                if x.get("diff"): lines += ["","LINE-BY-LINE DIFFERENCE","-"*70,x["diff"]]
            p.write_text("\n".join(lines),encoding="utf-8")
            activity("REPORT",body.get("notes",""),{"report":str(p)})
            self.send_json(200,{"path":str(p),"name":name}); return

        if u=="/api/git":
            path=body.get("path") or DATA["local_path"]
            if not path: self.send_json(400,{"error":"Local project path is required"}); return
            r=git(body.get("args",[]),path)
            activity("GIT"," ".join(body.get("args",[])),{"path":path,"exit_code":r["code"]})
            self.send_json(200,r); return

        if u=="/api/backup":
            src=Path(body.get("path") or DATA["local_path"])
            if not src.is_dir(): self.send_json(400,{"error":"Backup source does not exist"}); return
            BACKUPS.mkdir(exist_ok=True)
            dst=BACKUPS/datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copytree(src,dst,ignore=shutil.ignore_patterns(".git","backups","reports"))
            activity("BACKUP",body.get("notes",""),{"path":str(dst)})
            self.send_json(200,{"path":str(dst)}); return

        self.send_json(404,{"error":"Unknown endpoint"})

    def log_message(self,*args): pass

if __name__=="__main__":
    print(f"VCU Local Git Manager: http://127.0.0.1:{DATA['port']}")
    ThreadingHTTPServer(("127.0.0.1",int(DATA["port"])),Handler).serve_forever()
