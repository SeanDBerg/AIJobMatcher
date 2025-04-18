{pkgs}: {
  deps = [
    pkgs.zlib
    pkgs.xcodebuild
    pkgs.cacert
    pkgs.xsimd
    pkgs.pkg-config
    pkgs.libxcrypt
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
