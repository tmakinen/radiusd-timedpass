Name:           radiusd-otp
Version:        0.1.0
Release:        1%{?dist}%{?git_hash:.%git_hash}
Summary:        Simple WSGI app to provide OTP passwords to RADIUS
License:        MIT
URL:            https://github.com/tmakinen/radiusd-otp
Source:         %{url}/archive/v%{version}/radiusd-otp-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros
Requires(post): systemd-units
Requires:       freeradius

Source1:        radiusd-otp.service
Source2:        radiusd-otp.tmpfiles.conf
Source3:        radiusd-otp.sysconfig

%description
Simple WSGI app to provide OTP passwords to RADIUS

%prep
%autosetup -n radiusd-otp-%{version}

%generate_buildrequires
%pyproject_buildrequires -R

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files '*'
install -d -m 0755 %{buildroot}/run/%{name}/
install -D -m 0644 %{SOURCE1} %{buildroot}%{_unitdir}/%{name}.service
install -D -m 0644 %{SOURCE2} %{buildroot}%{_tmpfilesdir}/%{name}.conf
install -D -m 0644 %{SOURCE3} %{buildroot}%{_sysconfdir}/sysconfig/radiusd-otp

%post
/bin/systemctl daemon-reload >/dev/null 2>&1 || :

%preun
if [ $1 -eq 0 ] ; then
    /bin/systemctl --no-reload disable radiusd-otp.service > /dev/null 2>&1 || :
    /bin/systemctl stop radiusd-otp.service > /dev/null 2>&1 || :
fi

%postun
/bin/systemctl daemon-reload >/dev/null 2>&1 || :
if [ "$1" -ge "1" ] ; then
    /bin/systemctl try-restart radiusd-otp.service >/dev/null 2>&1 || :
fi

%files -n radiusd-otp -f %{pyproject_files}
%doc README.md
%license LICENSE
%dir /run/%{name}/
%{_unitdir}/%{name}.service
%{_tmpfilesdir}/%{name}.conf
%config(noreplace) %{_sysconfdir}/sysconfig/radiusd-otp

%changelog
* Sat Apr 11 2026 Timo Mäkinen <tmakinen@foo.sh> - 0.1.0-1
- Initial version of package
