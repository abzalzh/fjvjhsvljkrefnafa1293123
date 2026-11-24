"""Start real Uvicorn processes, exercise HTTP, then stop them. No public deployment."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]


def check(demo):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory() as directory:
        env=os.environ.copy()
        env['SAPAR_DEMO_MODE']='true' if demo else 'false'
        env['DATABASE_URL']=f'sqlite:///{Path(directory).as_posix()}/smoke.db'
        env['SAPAR_DATA_DIR']=str(ROOT/'backend/tests/fixtures/demo' if demo else ROOT/'data')
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
                              cwd=ROOT/'backend',env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3,trust_env=False) as client:
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError(f'Uvicorn exited: {proc.returncode}')
                    try:
                        health=client.get('/api/health')
                        health.raise_for_status()
                        break
                    except httpx.TransportError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError('Startup timeout')
                request=json.loads((ROOT/'integration/examples/generate-request.json').read_text(encoding='utf-8'))
                response=client.post('/api/trips/generate',json=request)
                response.raise_for_status()
                result=response.json()
                assert result['status']==('success' if demo else 'no_results')
                assert health.json()['data_mode']==('demo' if demo else 'real')
                assert client.get('/docs').status_code==200
                assert client.get('/openapi.json').status_code==200
                print(json.dumps({'mode':health.json()['data_mode'],'health':health.status_code,'generate':response.status_code,
                                  'status':result['status'],'trips':len(result['trips'])}))
        finally:
            if os.name == 'nt' and proc.poll() is None:
                # Windows venv python.exe may launch a child interpreter.
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__=='__main__':
    check(False)
    check(True)
