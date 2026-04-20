terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

resource "docker_image" "gpu_node" {
  name = "gpu-node:latest"
  build {
    context    = "../docker"
    dockerfile = "Dockerfile.node"
  }
  triggers = {
    dockerfile_hash = filemd5("../docker/Dockerfile.node")
  }
}

resource "docker_network" "test_farm" {
  name   = "gpu-test-farm"
  driver = "bridge"
}

resource "docker_container" "gpu_node" {
  count    = var.node_count
  name     = "gpu-node-${count.index + 1}"
  image    = docker_image.gpu_node.image_id
  hostname = "gpu-node-${count.index + 1}"

  privileged = true
  restart    = "unless-stopped"

  networks_advanced {
    name = docker_network.test_farm.name
  }

  volumes {
    host_path      = "/var/run/docker.sock"
    container_path = "/var/run/docker.sock"
  }

  volumes {
    host_path      = abspath("../results/node-${count.index + 1}")
    container_path = "/opt/test_results"
  }
}
