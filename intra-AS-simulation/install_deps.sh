#!/usr/bin/env bash
MY_VERSION="-mseewer1.0"

# install intra-AS dependencies
sudo apt install -y python3-pip
sudo pip3 install -r requirements.txt


cd ~
installdir=$(pwd)

# install OSPF/Zebra and other routing protocols
# adapted from: http://docs.frrouting.org/projects/dev-guide/en/latest/building-frr-for-ubuntu1804.html
FRRVERSION="stable/8.3"

sudo apt update
sudo apt-get install -y \
   git autoconf automake libtool make libreadline-dev texinfo \
   pkg-config libpam0g-dev libjson-c-dev bison flex \
   libc-ares-dev python3-dev python3-sphinx \
   install-info build-essential libsnmp-dev perl libcap-dev \
   libelf-dev libunwind-dev

# install FRR dependency -> libyang
sudo apt install -y libpcre2-dev cmake
git clone https://github.com/CESNET/libyang.git
cd libyang
git checkout v2.0.0
mkdir build; cd build
cmake -D CMAKE_INSTALL_PREFIX:PATH=/usr \
      -D CMAKE_BUILD_TYPE:String="Release" ..
make
sudo make install
cd $installdir
echo "libyang dependency installed"


# build + install FRR
sudo groupadd -r -g 92 frr
sudo groupadd -r -g 85 frrvty
sudo adduser --system --ingroup frr --home /var/run/frr/ \
   --gecos "FRR suite" --shell /sbin/nologin frr
sudo usermod -a -G frrvty frr
sudo usermod -a -G frrvty root


# compile FRR
git clone https://github.com/frrouting/frr.git frr
cd frr
git checkout $FRRVERSION
./bootstrap.sh
./configure \
    --prefix=/usr \
    --includedir=\${prefix}/include \
    --bindir=\${prefix}/bin \
    --sbindir=\${prefix}/lib/frr \
    --libdir=\${prefix}/lib/frr \
    --libexecdir=\${prefix}/lib/frr \
    --localstatedir=/var/run/frr \
    --sysconfdir=/etc/frr \
    --with-moduledir=\${prefix}/lib/frr/modules \
    --with-libyang-pluginsdir=\${prefix}/lib/frr/libyang_plugins \
    --enable-configfile-mask=0640 \
    --enable-logfile-mask=0640 \
    --enable-snmp=agentx \
    --enable-multipath=64 \
    --enable-user=frr \
    --enable-group=frr \
    --enable-vty-group=frrvty \
    --with-pkg-git-version \
    --with-pkg-extra-version=$MY_VERSION
make
sudo make install

cd $installdir
echo "frr installed"




