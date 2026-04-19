Name:           radiusd-timedpass
Version:        0.1.0
Release:        1%{?git_hash:.%{git_hash}}%{?dist}
Summary:        Simple WSGI app to provide OTP passwords to RADIUS
License:        MIT
URL:            https://github.com/tmakinen/radiusd-timedpass
Source:         %{url}/archive/v%{version}/radiusd-timedpass-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  selinux-policy-devel
BuildRequires:  systemd-rpm-macros
Requires(post): policycoreutils, systemd-units, systemd
Requires(postun): policycoreutils
Requires:       freeradius
Requires:       python3-freeradius

Source1:        radiusd-timedpass.service
Source2:        radiusd-timedpass.tmpfiles.conf
Source3:        radiusd-timedpass.sysconfig
Source4:        radiusd-timedpass.mod-config
Source5:        timedpass.py
Source6:        radiusd-timedpass.te
Source7:        radiusd-timedpass.fc

%description
Simple WSGI app to provide OTP passwords to RADIUS

%prep
%autosetup -n radiusd-timedpass-%{version}

%generate_buildrequires
%pyproject_buildrequires -R
cp %{SOURCE6} %{SOURCE7} .

%build
%pyproject_wheel
make -f %{_datadir}/selinux/devel/Makefile radiusd-timedpass.pp

%install
%pyproject_install
%pyproject_save_files '*'
install -d -m 0755 %{buildroot}/run/%{name}/
install -D -m 0644 %{SOURCE1} %{buildroot}%{_unitdir}/%{name}.service
install -D -m 0644 %{SOURCE2} %{buildroot}%{_tmpfilesdir}/%{name}.conf
install -D -m 0644 %{SOURCE3} %{buildroot}%{_sysconfdir}/sysconfig/radiusd-timedpass
install -D -m 0640 %{SOURCE4} %{buildroot}%{_sysconfdir}/raddb/mods-available/timedpass
mkdir -p %{buildroot}%{_sysconfdir}/raddb/mods-enabled
ln -sf ../mods-available/timedpass %{buildroot}%{_sysconfdir}/raddb/mods-enabled/timedpass
install -D -m 0755 %{SOURCE5} %{buildroot}%{_sysconfdir}/raddb/mods-config/python3/timedpass.py
install -D -m 0644 radiusd-timedpass.pp %{buildroot}%{_datadir}/selinux/packages/radiusd-timedpass.pp

%post
/usr/sbin/semodule -i %{_datadir}/selinux/packages/radiusd-timedpass.pp || :
/usr/bin/systemd-tmpfiles --create %{_tmpfilesdir}/radiusd-timedpass.conf || :
/sbin/restorecon -R /run/radiusd-timedpass || :
/bin/systemctl daemon-reload >/dev/null 2>&1 || :

%preun
if [ $1 -eq 0 ] ; then
    /bin/systemctl --no-reload disable radiusd-timedpass.service > /dev/null 2>&1 || :
    /bin/systemctl stop radiusd-timedpass.service > /dev/null 2>&1 || :
fi

%postun
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ "$1" -ge "1" ] ; then
    /bin/systemctl try-restart radiusd-timedpass.service >/dev/null 2>&1 || :
fi
if [ $1 -eq 0 ]; then
    # Remove the policy module when the package is uninstalled
    /usr/sbin/semodule -r radiusd-timedpass || :
fi

%files -n radiusd-timedpass -f %{pyproject_files}
%doc README.md
%license LICENSE
%dir /run/%{name}/
%{_unitdir}/%{name}.service
%{_tmpfilesdir}/%{name}.conf
%attr(0640,root,radiusd) %{_sysconfdir}/raddb/mods-available/timedpass
%attr(0777,root,radiusd) %{_sysconfdir}/raddb/mods-enabled/timedpass
%attr(0755,root,root) %{_sysconfdir}/raddb/mods-config/python3/timedpass.py
%{_datadir}/selinux/packages/radiusd-timedpass.pp
%config(noreplace) %{_sysconfdir}/sysconfig/radiusd-timedpass

%changelog
* Sat Apr 11 2026 Timo Mäkinen <tmakinen@foo.sh> - 0.1.0-1
- Initial version of package
