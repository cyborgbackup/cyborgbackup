Vagrant.configure("2") do |config|
  config.vm.define "cyborgbackup" do |subvm|
    subvm.vm.box = "debian/bookworm64"
    subvm.vm.hostname = "cyborgbackup"
    subvm.vm.network "private_network", type: "dhcp"
  end
  config.vm.provider "virtualbox" do |v|
    v.memory = 4096
    v.cpus = 2
  end
end
