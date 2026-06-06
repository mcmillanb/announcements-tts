# announcements-tts troubleshooting guide

This guide is for the airgap/GPU deployment on aibox.

Repo path on the host:

```bash
cd /home/billy/code/announcements-tts
```

## What healthy looks like

The stack is healthy when all of these are true:

```bash
nvidia-smi

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8766/health
curl -fsS http://127.0.0.1:8767/health
```

Expected result:
- `nvidia-smi` shows the RTX 3050 and a driver version
- `tts` is `Up ... (healthy)` on port 8765
- `bundled-tts` is healthy on port 8766
- `f5-tts` is healthy on port 8767
- `/health` returns `tts_status":"ready"`

## Fast triage checklist

Run these first:

```bash
cd /home/billy/code/announcements-tts

nvidia-smi
modprobe nvidia
lsmod | grep -i nvidia

uname -r
dkms status

sudo journalctl -b | grep -i -E 'nvidia|nouveau|dkms|secure' | tail -n 100

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps -a

docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=100 tts

docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=100 bundled-tts

docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=100 f5-tts

curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8766/health
curl -fsS http://127.0.0.1:8767/health

df -h /
docker system df -v
```

If you only want a short summary, check these three first:

```bash
nvidia-smi

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps -a
curl -fsS http://127.0.0.1:8765/health
```

## Scenario 1: NVIDIA driver is missing or the module is not loaded

Symptoms:
- `nvidia-smi` fails
- `modprobe nvidia` says module not found
- Docker containers fail with `nvml error: driver not loaded`
- `bundled-tts` and `f5-tts` sit in `Created` or fail immediately

Diagnosis:

```bash
nvidia-smi
modprobe nvidia
lsmod | grep -i nvidia
uname -r
journalctl -k -b | grep -i -E 'nvidia|nouveau|module|signature' | tail -n 100
```

What to fix:
- install the matching DKMS package for the running kernel
- make sure kernel headers are installed
- reboot after the driver install

Typical repair on this box:

```bash
sudo apt update
sudo apt install dkms build-essential linux-headers-$(uname -r) nvidia-dkms-590-open nvidia-driver-590-open
sudo reboot
```

If Ubuntu already has the prebuilt module package for the exact kernel, this can work too:

```bash
sudo apt update
sudo apt install linux-modules-nvidia-590-open-$(uname -r) nvidia-driver-590-open
sudo reboot
```

After reboot:

```bash
nvidia-smi
modprobe nvidia
```

If `nvidia-smi` still fails after install + reboot, the next thing to check is Secure Boot or a kernel/package mismatch.

## Scenario 2: DKMS is missing or not built for the current kernel

Symptoms:
- `dkms: command not found`
- `dkms status` is empty or shows no NVIDIA entry for the current kernel
- `nvidia-smi` still fails even though NVIDIA packages are installed

Diagnosis:

```bash
uname -r
dpkg -l | grep -E '^ii\s+dkms|^ii\s+nvidia-dkms|^ii\s+linux-headers-'
dkms status
```

Fix:

```bash
sudo apt update
sudo apt install dkms build-essential linux-headers-$(uname -r) nvidia-dkms-590-open nvidia-driver-590-open
sudo reboot
```

Verification:

```bash
dkms status
nvidia-smi
modprobe nvidia
```

## Scenario 3: NVIDIA is working on the host, but Docker still says NVML/driver not loaded

Symptoms:
- `nvidia-smi` works on the host
- Docker containers fail to start with `nvidia-container-cli: initialization error`
- Compose starts the main app, but GPU services fail

Diagnosis:

```bash
docker info | grep -i -E 'runtimes|default runtime|nvidia'
docker run --rm --gpus all nvidia/cuda:12.1.0-cudnn8-runtime nvidia-smi
```

Fixes to try:

```bash
sudo systemctl restart docker
```

If Docker is missing the NVIDIA runtime config, reconfigure it:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Then retry:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-cudnn8-runtime nvidia-smi
```

If that succeeds, bring the stack up again:

```bash
cd /home/billy/code/announcements-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --remove-orphans
```

## Scenario 4: Main app is up, but bundled-tts or f5-tts is stuck in Created or unhealthy

Symptoms:
- `tts` is healthy on 8765
- `bundled-tts` or `f5-tts` is `Created`, `starting`, or missing
- `/health` says bundled provider is unreachable
- DNS errors like `Temporary failure in name resolution` or `All connection attempts failed`

Diagnosis:

```bash
cd /home/billy/code/announcements-tts

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps -a

docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=120 bundled-tts

docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=120 f5-tts
curl -fsS http://127.0.0.1:8765/health
```

Fix:

```bash
cd /home/billy/code/announcements-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d bundled-tts f5-tts
```

Then verify:

```bash
docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8766/health
curl -fsS http://127.0.0.1:8767/health
```

If the logs are empty, the service may have never started because the GPU runtime failed earlier. Go back to Scenario 1 or 3.

## Scenario 5: Port clash from a stale container

Symptoms:
- compose says a service cannot bind to 8765, 8766, or 8767
- an old container from a previous stack is still running
- a non-airgap CPU container is occupying 8767

Diagnosis:

```bash
docker ps --format '{{.Names}} {{.Ports}} {{.Status}}' | grep announcement-tts
lsof -nP -iTCP:8765 -sTCP:LISTEN
lsof -nP -iTCP:8766 -sTCP:LISTEN
lsof -nP -iTCP:8767 -sTCP:LISTEN
```

Fix:

```bash
cd /home/billy/code/announcements-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml down --remove-orphans
```

If a legacy standalone container is still around, remove it directly:

```bash
docker rm -f announcement-tts-f5-cpu
```

Then bring the stack back up:

```bash
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --remove-orphans
```

## Scenario 6: Disk full or Docker build fails with no space left on device

Symptoms:
- build stops with `no space left on device`
- Docker image build gets far and then dies at the end
- `df -h /` shows the disk near 100%
- `docker system df -v` shows a large build cache

Diagnosis:

```bash
df -h /
docker system df -v
```

Low-risk cleanup first:

```bash
docker builder prune -af
```

If you still need more space, be more aggressive but understand the impact:

```bash
docker system prune -af
```

Only remove volumes if you are sure you do not need cached model/data volumes:

```bash
docker volume prune
```

After cleanup, check free space again:

```bash
df -h /
```

Then rebuild or restart the stack:

```bash
cd /home/billy/code/announcements-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --build --remove-orphans
```

## Scenario 7: The main API is up, but bundled provider still says unavailable

Symptoms:
- `/health` returns `status: ok`
- `tts_status` is `unavailable`
- message mentions bundled provider unreachable

Diagnosis:

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8766/health
```

If the main app can’t reach `http://bundled-tts:8001`, check the container network and aliases:

```bash
cd /home/billy/code/announcements-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps

docker inspect announcement-tts-models-airgap --format '{{json .NetworkSettings.Networks}}' | jq
```

Quick restart of the stack:

```bash
cd /home/billy/code/announcements-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml restart bundled-tts tts
```

If DNS resolution still fails, inspect the container logs and restart the whole stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=120 bundled-tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml logs --tail=120 tts
docker compose -f docker-compose.yml -f docker-compose.airgap.yml down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --remove-orphans
```

## Scenario 8: The stack is half-up after a reboot

Symptoms:
- `tts` is healthy
- model services are not ready yet
- the host GPU looks fixed but services were not restarted

Recovery sequence:

```bash
cd /home/billy/code/announcements-tts

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps -a
nvidia-smi

docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --remove-orphans
sleep 10

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps
curl -fsS http://127.0.0.1:8765/health
```

## Recommended full recovery sequence

If you want the safest “start from scratch” flow for this stack:

```bash
cd /home/billy/code/announcements-tts

docker compose -f docker-compose.yml -f docker-compose.airgap.yml down --remove-orphans

nvidia-smi

docker builder prune -af

# only if you know the GPU driver is loaded and Docker has the runtime configured:
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --build --remove-orphans

sleep 10

docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8766/health
curl -fsS http://127.0.0.1:8767/health
```

## Notes from the aibox incident

The failure we hit was a classic chain:
- disk filled up during a long image build
- the build completed but the metadata write failed
- after reboot, the NVIDIA kernel module was missing for the running kernel
- Docker then failed with NVML/driver errors
- once the driver package and DKMS module were corrected, the stack started cleanly

If you see that same pattern again, start with `nvidia-smi`, `modprobe nvidia`, `dkms status`, and `docker compose ps -a`.

## Aibox quick fix cheat sheet

Use this when you do not want the full diagnosis path.

```bash
cd /home/billy/code/announcements-tts

# 1) Is the GPU driver alive?
nvidia-smi

# 2) Can the kernel load the module?
modprobe nvidia

# 3) Is DKMS built for this kernel?
dkms status

# 4) Are the containers up or stuck?
docker compose -f docker-compose.yml -f docker-compose.airgap.yml ps -a

# 5) If the stack is half-up, start it cleanly

docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --remove-orphans

# 6) If a stale container is blocking ports

docker rm -f announcement-tts-f5-cpu

# 7) If disk is full and builds are failing

docker builder prune -af

df -h /

# 8) Final verification
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8766/health
curl -fsS http://127.0.0.1:8767/health
```

Quick decision tree:
- `nvidia-smi` fails: fix the host NVIDIA driver / DKMS first
- `modprobe nvidia` says module not found: install the matching NVIDIA DKMS module for the running kernel
- `docker` errors with `nvml error: driver not loaded`: Docker can see the GPU runtime, but the host driver is still broken
- services are `Created`: run `up -d --remove-orphans`
- port clash: remove stale legacy containers
- `no space left on device`: prune builder cache before rebuilding

Minimal fix sequence when in doubt:

```bash
sudo apt update
sudo apt install dkms build-essential linux-headers-$(uname -r) nvidia-dkms-590-open nvidia-driver-590-open
sudo reboot

cd /home/billy/code/announcements-tts
docker builder prune -af
docker compose -f docker-compose.yml -f docker-compose.airgap.yml up -d --remove-orphans
curl -fsS http://127.0.0.1:8765/health
```
