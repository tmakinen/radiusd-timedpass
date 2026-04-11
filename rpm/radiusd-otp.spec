Name:           python-radiusd-otp
Version:        0.1.0
Release:        1%{?dist}{?git_hash:.%git_hash}
Summary:        Simple WSGI app to provide OTP passwords to RADIUS
License:        MIT
URL:            https://github.com/tmakinen/radiusd-otp
Source:         %{url}/archive/v%{version}/radiusd-otp-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros

%description
Simple WSGI app to provide OTP passwords to RADIUS

%package -n python3-radiusd-otp
Summary:        %{summary}

%description -n python3-radiusd-otp
Simple WSGI app to provide OTP passwords to RADIUS

%prep
%autosetup -n radiusd-otp-%{version}

%generate_buildrequires
%pyproject_buildrequires -R

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files radiusd_otp

%files -n python3-radiusd-otp -f %{pyproject_files}
%doc README.md
%license LICENSE

%changelog
* Sat Apr 11 2026 Timo Mäkinen <tmakinen@foo.sh> - 0.1.0-1
- Initial version of package
