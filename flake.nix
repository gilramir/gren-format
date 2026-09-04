{
  description = "A code formatter for the Gren programming language";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
  };

  outputs = { nixpkgs, ... }: {
    packages = builtins.mapAttrs (system: pkgs: {
      default = pkgs.stdenv.mkDerivation {
        pname = "gren-format";
        version = "1.3.0";

        __structuredAttrs = true;
        strictDeps = true;

        src = ./.;

        buildInputs = with pkgs; [
          nodejs
        ];

        nativeBuildInputs = with pkgs; [
          gren
        ];

        buildPhase = ''
          runHook preBuild

          ./build.sh

          runHook postBuild
        '';

        installPhase = ''
          runHook preInstall

          install -Dm755 app $out/bin/gren-format

          runHook postInstall
        '';
      };
    }) nixpkgs.legacyPackages;

    devShells = builtins.mapAttrs (system: pkgs: {
      default = pkgs.mkShell {
        packages = with pkgs; [
          nodejs_22
          gren
        ];
      };
    }) nixpkgs.legacyPackages;
  };
}
