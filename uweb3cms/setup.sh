#!/bin/bash
apt install nginx mariadb-server
mysql_secure_installation
ln -sf ./ /opt/cms/
ln -sf cms.service /etc/systemd/system/cms.service
systemctl enable --now cms.service
