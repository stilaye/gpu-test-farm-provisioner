# KVM/libvirt Terraform config — deploy on Ubuntu 22.04 Linux host (AWS EC2 m5.xlarge)
# Phase 2: After validating Mac variant, swap this in:
#   cp terraform/kvm/main.tf terraform/main.tf
#   cp ansible/inventory/hosts_ssh.yml ansible/inventory/hosts.yml
#   make all

terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "~> 0.7"
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}

# Ubuntu 22.04 cloud image (downloaded once, reused as base)
resource "libvirt_volume" "ubuntu_base" {
  name   = "ubuntu-22.04-base.qcow2"
  pool   = "default"
  source = "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img"
  format = "qcow2"
}

# Per-node disk cloned from base
resource "libvirt_volume" "node_disk" {
  count          = var.node_count
  name           = "gpu-node-${count.index + 1}.qcow2"
  base_volume_id = libvirt_volume.ubuntu_base.id
  pool           = "default"
  size           = 21474836480 # 20 GB
}

# Cloud-init user data for SSH key injection and hostname
data "template_file" "user_data" {
  count    = var.node_count
  template = file("${path.module}/cloud_init.cfg")
  vars = {
    hostname   = "gpu-node-${count.index + 1}"
    public_key = file("~/.ssh/id_rsa.pub")
  }
}

resource "libvirt_cloudinit_disk" "init" {
  count     = var.node_count
  name      = "gpu-node-${count.index + 1}-init.iso"
  pool      = "default"
  user_data = data.template_file.user_data[count.index].rendered
}

# NAT network for test nodes
resource "libvirt_network" "test_net" {
  name      = "gpu-test-farm"
  mode      = "nat"
  addresses = ["192.168.122.0/24"]
  dhcp {
    enabled = true
  }
  dns {
    enabled = true
  }
}

# The GPU test node VMs
resource "libvirt_domain" "gpu_node" {
  count  = var.node_count
  name   = "gpu-node-${count.index + 1}"
  memory = 2048
  vcpu   = 2

  cloudinit = libvirt_cloudinit_disk.init[count.index].id

  network_interface {
    network_id     = libvirt_network.test_net.id
    hostname       = "gpu-node-${count.index + 1}"
    wait_for_lease = true
  }

  disk {
    volume_id = libvirt_volume.node_disk[count.index].id
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  graphics {
    type        = "spice"
    listen_type = "address"
    autoport    = true
  }
}

output "node_ips" {
  description = "IP addresses of KVM GPU test nodes"
  value       = libvirt_domain.gpu_node[*].network_interface[0].addresses[0]
}

variable "node_count" {
  description = "Number of KVM GPU test node VMs"
  type        = number
  default     = 2
}
