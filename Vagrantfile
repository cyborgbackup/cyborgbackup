Vagrant.configure("2") do |config|
  config.vm.define "cyborgbackup" do |subvm|
    subvm.vm.box = "debian/stretch64"
    subvm.vm.hostname = "cyborgbackup"
    subvm.vm.network "private_network", type: "dhcp"
  end
end
