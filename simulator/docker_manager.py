# edos_docker_simulation/docker_manager.py
import docker
from pathlib import Path
from simulator.experiment_config import ServerConfig
import time
import subprocess # For the 'docker stats' CPU workaround
from simulator import config # Import your configuration

try:
    client = docker.from_env(environment={"DOCKER_HOST": config.DOCKER_ENGINE_SOCKET})
except docker.errors.DockerException as e:
    print(f"FATAL: Could not connect to Docker daemon. Is Docker running? Error: {e}")
    print("Ensure Docker is installed, running, and your user has permissions.")
    exit(1) # Exit if Docker is not accessible

def build_docker_image():
    print(f"Attempting to build Docker image: {config.DOCKER_IMAGE_NAME}...")
    try:
        # Check if image already exists to save time, though build usually handles this with cache
        try:
            client.images.get(config.DOCKER_IMAGE_NAME)
            print(f"Image {config.DOCKER_IMAGE_NAME} already exists. Skipping build.")
            return True
        except docker.errors.ImageNotFound:
            print(f"Image {config.DOCKER_IMAGE_NAME} not found. Proceeding with build.")

        image, build_log = client.images.build(
            path=str(Path(__file__).resolve().parents[1]),  # Repository build context
            dockerfile="Dockerfile",
            tag=config.DOCKER_IMAGE_NAME,
            rm=True # Remove intermediate containers after a successful build
        )
        print(f"Image {image.short_id} built successfully and tagged as {config.DOCKER_IMAGE_NAME}.")
        # for line in build_log: # Uncomment to see detailed build log
        #     if 'stream' in line:
        #         print(line['stream'].strip())
        return True
    except docker.errors.BuildError as e:
        print(f"ERROR: Docker image build failed for {config.DOCKER_IMAGE_NAME}.")
        for line in e.build_log:
            if 'stream' in line:
                print(line['stream'].strip())
        return False
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during image build: {e}")
        return False

def ensure_docker_network():
    try:
        client.networks.get(config.DOCKER_NETWORK_NAME)
        print(f"Docker network '{config.DOCKER_NETWORK_NAME}' already exists.")
    except docker.errors.NotFound:
        print(f"Creating Docker network '{config.DOCKER_NETWORK_NAME}'...")
        try:
            client.networks.create(config.DOCKER_NETWORK_NAME, driver="bridge")
            print(f"Docker network '{config.DOCKER_NETWORK_NAME}' created successfully.")
        except docker.errors.APIError as e:
            print(f"ERROR: Failed to create Docker network '{config.DOCKER_NETWORK_NAME}': {e}")
            return False
    return True


def start_instance(instance_numeric_id, server=None, *, publish_ports=True, diagnostic_directory=None, diagnostic_capacity=4096):
    """
    Starts a new container instance.
    instance_numeric_id: An integer (e.g., 1, 2, 3) to make container name and port unique.
    Returns the container object if successful, None otherwise.
    """
    server = server or ServerConfig()
    container_name = f"{config.BASE_CONTAINER_NAME}_{instance_numeric_id}"
    # Calculate host port based on base port + (id - 1) to ensure uniqueness
    # e.g., if id is 1, port is STARTING_HOST_PORT. if id is 2, port is STARTING_HOST_PORT + 1
    host_port = config.STARTING_HOST_PORT + (instance_numeric_id - 1)

    print(f"Attempting to start container {container_name}: " +
          (f"container:80 to host:{host_port}" if publish_ports else "network only, no host publication"))
    try:
        # Check if a container with the same name already exists (maybe from a failed previous run)
        try:
            existing_container = client.containers.get(container_name)
            if existing_container.status == 'running':
                print(f"Container {container_name} is already running.")
                return existing_container
            else:
                print(f"Removing existing stopped container {container_name} before starting anew.")
                existing_container.remove(force=True)
        except docker.errors.NotFound:
            pass # Good, no existing container with that name

        diagnostic_options = {}
        if diagnostic_directory is not None:
            diagnostic_options['volumes'] = {str(Path(diagnostic_directory).resolve()):{'bind':'/diagnostics','mode':'rw'}}
        container = client.containers.run(
            config.DOCKER_IMAGE_NAME,
            detach=True,
            name=container_name,
            ports={f'{config.APP_CONTAINER_PORT}/tcp': host_port} if publish_ports else {},
            network=config.DOCKER_NETWORK_NAME,
            restart_policy={"Name": "no"}, # Do not auto-restart for this simulation
            environment={
                "INSTANCE_MAX_CONCURRENT_REQUESTS": str(server.process_pool_workers),
                "WORK_UNITS": str(server.default_work_units),
                "PROCESSING_TIME": str(server.default_sleep_seconds),
                "APP_PORT": str(config.APP_CONTAINER_PORT),
                **({'EDOS_DIAGNOSTIC_PATH':'/diagnostics/events.jsonl',
                    'EDOS_DIAGNOSTIC_STOP':'/diagnostics/stop',
                    'EDOS_DIAGNOSTIC_CAPACITY':str(diagnostic_capacity)} if diagnostic_directory is not None else {})
            },
            **diagnostic_options,
        )
        print(f"Container {container.short_id} ({container_name}) started. " +
              (f"Accessible on host port {host_port}." if publish_ports else "Docker network only; no published port."))
        # Optional: wait a tiny bit for the app inside the container to start
        time.sleep(0.5)
        return container
    except docker.errors.APIError as e:
        print(f"ERROR: Failed to start container {container_name}: {e}")
        return None
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while starting container {container_name}: {e}")
        return None

def stop_instance(container_name_or_id):
    """Stops and removes a container."""
    print(f"Attempting to stop and remove container {container_name_or_id}...")
    try:
        container = client.containers.get(container_name_or_id)
        container.stop(timeout=5) # Give 5 seconds to stop gracefully
        container.remove(force=True) # Force remove if stop fails or for quick cleanup
        print(f"Container {container_name_or_id} stopped and removed.")
        return True
    except docker.errors.NotFound:
        print(f"Container {container_name_or_id} not found. Nothing to stop/remove.")
        return False # Or True if "not found" means "already gone"
    except docker.errors.APIError as e:
        print(f"ERROR: Failed to stop/remove container {container_name_or_id}: {e}")
        return False
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while stopping/removing {container_name_or_id}: {e}")
        return False

def get_active_instances_by_base_name():
    """
    Returns a list of running container objects that match our BASE_CONTAINER_NAME.
    """
    active_containers = []
    try:
        all_containers = client.containers.list(filters={"name": f"^{config.BASE_CONTAINER_NAME}_"})
        for container in all_containers:
            if container.status == 'running': # Double check status
                active_containers.append(container)
    except docker.errors.APIError as e:
        print(f"ERROR: Failed to list active containers: {e}")
    return active_containers

def get_container_cpu_percent(container_name_or_id):
    """
    Gets CPU percentage for a container using 'docker stats'.
    This is a workaround as the Docker API for stats is complex for CPU %.
    """
    try:
        cmd = ["docker", "--host", config.DOCKER_ENGINE_SOCKET, "stats", str(container_name_or_id), "--no-stream", "--format", "{{.CPUPerc}}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=3)

        if result.returncode != 0:
            # print(f"Warning: 'docker stats' for {container_name_or_id} failed or returned non-zero. Stderr: {result.stderr.strip()}")
            return 0.0

        cpu_str = result.stdout.strip().replace('%', '')
        if cpu_str:
            return float(cpu_str)
        return 0.0
    except subprocess.TimeoutExpired:
        print(f"Warning: 'docker stats' for {container_name_or_id} timed out.")
        return 0.0
    except subprocess.CalledProcessError as e: # Should be caught by check=False now
        # print(f"Warning: 'docker stats' for {container_name_or_id} failed. Stderr: {e.stderr.strip()}")
        return 0.0
    except FileNotFoundError:
        print("ERROR: Command 'docker' not found. Is Docker installed and in PATH?")
        return 0.0 # Or raise an exception
    except ValueError:
        # print(f"Warning: Could not convert CPU output to float for {container_name_or_id}. Output: '{cpu_str}'")
        return 0.0
    except Exception as e:
        # print(f"Warning: Unexpected error getting CPU for {container_name_or_id}: {e}")
        return 0.0


def get_container_stats(container_obj):
    """
    Returns a dict with {'cpu_percent': float, 'memory_usage_mb': float} for a given container object.
    """
    if not container_obj:
        return {"cpu_percent": 0.0, "memory_usage_mb": 0.0}

    cpu_p = get_container_cpu_percent(container_obj.name) # Use the name for docker stats

    mem_usage_mb = 0.0
    try:
        # Get live stats (stream=False gets a single snapshot)
        stats = container_obj.stats(stream=False, decode=True)
        if stats and 'memory_stats' in stats and 'usage' in stats['memory_stats']:
            mem_usage_mb = stats['memory_stats']['usage'] / (1024 * 1024) # Convert bytes to MB
    except docker.errors.NotFound:
        # print(f"Warning: Container {container_obj.name} not found while getting memory stats (likely just removed).")
        pass # Container might have been removed between getting the object and stats
    except Exception as e:
        # print(f"Warning: Error getting memory stats for {container_obj.name}: {e}")
        pass

    return {"cpu_percent": cpu_p, "memory_usage_mb": mem_usage_mb}

def cleanup_all_simulation_instances():
    print("Cleaning up all simulation instances...")
    # List containers based on the naming convention used in this simulation
    # This is safer than removing all containers on the system.
    # Filters: name uses regex. ^ means starts with.
    simulation_containers = client.containers.list(all=True, filters={"name": f"^{config.BASE_CONTAINER_NAME}_"})
    if not simulation_containers:
        print("No simulation instances found to clean up.")
        return

    for container in simulation_containers:
        print(f"Stopping and removing container: {container.name} ({container.short_id})...")
        try:
            container.stop(timeout=2) # Quick timeout
        except docker.errors.APIError as e:
            if 'is already stopped' not in str(e).lower(): # Ignore if already stopped
                print(f"  Warning: Could not stop {container.name}: {e}")
        try:
            container.remove(force=True)
            print(f"  Container {container.name} removed.")
        except docker.errors.APIError as e:
            print(f"  Warning: Could not remove {container.name}: {e}")
    print("Simulation instance cleanup complete.")



# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    print("--- Running docker_manager.py self-test ---")

    if not build_docker_image():
        print("Self-test failed: Image build error.")
        exit(1)

    if not ensure_docker_network():
        print("Self-test failed: Network creation error.")
        exit(1)
    
    cleanup_all_simulation_instances() # Clean before test

    print("\nTesting instance start (should be 1 instance)...")
    # instance_numeric_id=1 means host port will be config.STARTING_HOST_PORT (e.g. 8080)
    c1 = start_instance(1) 
    if not c1:
        print("Self-test failed: Could not start instance 1.")
        exit(1)

    print(f"Instance c1 ({c1.name if c1 else 'None'}) created.")

    # CRITICAL DEBUGGING: Inspect container attributes immediately after start and reload
    print("\n--- CRITICAL DEBUG: Inspecting c1 attributes ---")
    if c1:
        try:
            print(f"Reloading attributes for c1 ({c1.name})...")
            c1.reload() # Crucial: Ensure attributes are fresh from the Docker daemon
            print(f"Attributes reloaded. Status after reload: {c1.status}")

            if 'NetworkSettings' in c1.attrs:
                network_settings = c1.attrs['NetworkSettings']
                print("  'NetworkSettings' found.")

                if 'Ports' in network_settings:
                    ports_info = network_settings['Ports']
                    print(f"  'Ports' found. Content of Ports (type: {type(ports_info)}):")
                    print(f"  PORTS_INFO_START>>>{ports_info}<<<PORTS_INFO_END") # This will show us exactly what keys are present

                    # Now, let's try to access '80/tcp' safely based on what we see above
                    if ports_info and isinstance(ports_info, dict):
                        if '80/tcp' in ports_info:
                            print("    Key '80/tcp' IS present in Ports.")
                            mapping_80_tcp = ports_info['80/tcp']
                            print(f"    Value for '80/tcp' (type: {type(mapping_80_tcp)}): {mapping_80_tcp}")
                            if mapping_80_tcp and isinstance(mapping_80_tcp, list) and len(mapping_80_tcp) > 0:
                                host_port_detail = mapping_80_tcp[0]
                                print(f"    First mapping detail (type: {type(host_port_detail)}): {host_port_detail}")
                                if 'HostPort' in host_port_detail:
                                    print(f"    SUCCESS: HostPort found: {host_port_detail['HostPort']}")
                                else:
                                    print("    ERROR: 'HostPort' key NOT found in the first mapping detail.")
                            else:
                                print("    ERROR: '80/tcp' mapping is None, not a list, or an empty list.")
                        else:
                            print("    ERROR: Key '80/tcp' IS NOT present in Ports dictionary.")
                            print(f"    Available keys in Ports: {list(ports_info.keys())}")
                    else:
                        print("    ERROR: ports_info is None or not a dictionary.")
                else:
                    print("  ERROR: 'Ports' key NOT found in NetworkSettings.")
                
                if 'Networks' in network_settings and config.DOCKER_NETWORK_NAME in network_settings['Networks']:
                     network_details = network_settings['Networks'][config.DOCKER_NETWORK_NAME]
                     print(f"  IP for '{config.DOCKER_NETWORK_NAME}': {network_details.get('IPAddress')}")
                else:
                    print(f"  ERROR: Network '{config.DOCKER_NETWORK_NAME}' not found in NetworkSettings.Networks.")
            else:
                print("  ERROR: 'NetworkSettings' key NOT found in c1.attrs.")
        except Exception as e_debug:
            print(f"  EXCEPTION during c1 attribute inspection: {e_debug}")
            import traceback
            traceback.print_exc()
    else:
        print("c1 object is None, cannot inspect attributes.")
    print("--- END CRITICAL DEBUG ---\n")

    # Attempt to print IP and Port again, now that we hopefully understand the structure
    print("Attempting to retrieve and print IP and Host Port more safely:")
    if c1:
        try:
            c1.reload() # Reload again just to be absolutely sure
            ip_address = c1.attrs.get('NetworkSettings', {}).get('Networks', {}).get(config.DOCKER_NETWORK_NAME, {}).get('IPAddress')
            
            port_mappings_dict = c1.attrs.get('NetworkSettings', {}).get('Ports', {})
            host_port_str = "Not found"

            if '80/tcp' in port_mappings_dict:
                mapping_list = port_mappings_dict['80/tcp']
                if mapping_list and isinstance(mapping_list, list) and len(mapping_list) > 0:
                    host_port_str = mapping_list[0].get('HostPort', "HostPort key missing")
            elif port_mappings_dict: # If '80/tcp' is not there, print what IS there
                host_port_str = f"Key '80/tcp' not found. Available port keys: {list(port_mappings_dict.keys())}"


            print(f"Instance 1 ({c1.name}) IP on '{config.DOCKER_NETWORK_NAME}': {ip_address if ip_address else 'Not found'}")
            print(f"Instance 1 ({c1.name}) Mapped Host Port for 80/tcp: {host_port_str}")

        except Exception as e_final_print:
            print(f"Error during final print attempt: {e_final_print}")

    print("\nTesting get_active_instances_by_base_name...")
    active = get_active_instances_by_base_name()
    if c1 and len(active) == 1 and active[0].name == c1.name: # Check c1 is not None
        print(f"Correctly found 1 active instance: {active[0].name}")
    elif not c1 and not active: # If c1 failed to start and no active instances, that's consistent.
        print("c1 failed to start and no active instances found, which is consistent.")
    else:
        print(f"Self-test issue: Expected 1 active instance named {c1.name if c1 else 'N/A'}, found {len(active)}. Instances: {[c.name for c in active]}")
        # Don't exit here if c1 was None, allow cleanup to run
        # if c1: exit(1)

    print("\nTesting get_container_stats for instance 1...")
    if c1: # Only get stats if c1 is valid
        print("Waiting a few seconds for stats to populate...")
        time.sleep(3)
        stats1 = get_container_stats(c1)
        print(f"Stats for {c1.name}: CPU {stats1['cpu_percent']:.2f}%, Memory {stats1['memory_usage_mb']:.2f}MB")
        if stats1['cpu_percent'] < 0 :
             print(f"Warning: CPU percent seems off for {c1.name}")
    else:
        print("Skipping stats test as c1 was not successfully created/retrieved.")

    print("\nTesting instance stop for instance 1...")
    if c1: # Only stop if c1 is valid
        if not stop_instance(c1.name):
            print(f"Self-test warning: Could not stop instance {c1.name} (might have already been stopped or failed to start fully)")
        else:
            try:
                # Attempt to get it again to confirm removal
                client.containers.get(c1.name) 
                print(f"Self-test failed: Instance {c1.name} still exists after stop_instance call.")
            except docker.errors.NotFound:
                print(f"Instance {c1.name} correctly removed or was never fully registered for stop.")
    else:
        print("Skipping stop test for c1 as it was not successfully created/retrieved.")

    print("\nTesting cleanup_all_simulation_instances (should be none left)...")
    c2 = start_instance(2)
    c3 = start_instance(3)
    if c2 and c3:
         print("Started c2 and c3 for cleanup test.")
    elif c2:
        print("Started c2 for cleanup test (c3 failed).")
    elif c3:
        print("Started c3 for cleanup test (c2 failed).")
    else:
        print("Failed to start c2 or c3 for cleanup test.")
        
    cleanup_all_simulation_instances()
    active_after_cleanup = get_active_instances_by_base_name()
    if not active_after_cleanup:
        print("Cleanup successful, no active simulation instances found.")
    else:
        print(f"Self-test failed: Cleanup left active instances: {[c.name for c in active_after_cleanup]}")

    print("\n--- docker_manager.py self-test complete ---")   
