"""Exercise the actual receiver image without joining the host's network."""
import re
import subprocess
import sys
import time


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=120).stdout


def smoke(image, platform):
    def invoke(program, *args):
        return run('docker', 'run', '--platform', platform, '--entrypoint', program, image, *args)

    version = invoke('/usr/local/bin/shairport-sync', '-V')
    for feature in ('AirPlay2', 'metadata', 'pipe', 'stdout'):
        if feature not in version:
            raise RuntimeError(f'Missing receiver feature: {feature}')
    nqptp = invoke('/usr/local/bin/nqptp', '-V')
    receiver_smi = re.search(r'smi\d+', version)
    timing_smi = re.search(r'smi\d+', nqptp)
    if not receiver_smi or not timing_smi or receiver_smi[0] != timing_smi[0]:
        raise RuntimeError('Receiver and NQPTP shared-memory interfaces do not match')
    print(version.strip(), flush=True)
    print(nqptp.strip(), flush=True)

    for mode, port in (('classic', 5000), ('airplay2', 7000)):
        container = run('docker', 'run', '-d', '--platform', platform, image,
                        f'--service-type={mode}', '-a', 'Receiver CI', '-o', 'dummy').strip()
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if run('docker', 'inspect', '--format', '{{.State.Running}}', container).strip() != 'true':
                    raise RuntimeError(f'{mode} receiver exited during startup')
                probe = subprocess.run(
                    ['docker', 'exec', container, '/bin/sh', '-ec',
                     'pidof shairport-sync && netstat -lnt'],
                    capture_output=True, text=True, timeout=15,
                )
                if probe.returncode == 0 and re.search(rf':{port}\s', probe.stdout):
                    timing = subprocess.run(['docker', 'exec', container, 'pidof', 'nqptp'],
                                            capture_output=True, text=True, timeout=15)
                    if (timing.returncode == 0) != (mode == 'airplay2'):
                        raise RuntimeError(f'Unexpected NQPTP startup for {mode}')
                    print(f'{platform}: {mode} startup and listener passed', flush=True)
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f'{mode} receiver did not open RTSP port {port}')
        except Exception:
            print(run('docker', 'logs', container), file=sys.stderr)
            raise
        finally:
            run('docker', 'stop', '--time', '10', container)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: smoke_receiver.py IMAGE PLATFORM')
    smoke(*sys.argv[1:])
