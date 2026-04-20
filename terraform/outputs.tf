output "node_names" {
  description = "Names of provisioned GPU test node containers"
  value       = docker_container.gpu_node[*].name
}

output "node_count" {
  description = "Number of active GPU test nodes"
  value       = length(docker_container.gpu_node)
}

output "network_name" {
  description = "Docker network name for the test farm"
  value       = docker_network.test_farm.name
}
