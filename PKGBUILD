# Maintainer: James Claridge
# Build from a local checkout:   makepkg -si
# For the AUR, point `source` at the published git repo (git+https://...).
pkgname=how-many-tokens-left
pkgver=0.1.0
pkgrel=1
pkgdesc="Waybar module showing 5-hour and weekly quota left on CLIProxyAPI Claude/Codex accounts"
arch=('any')
url="https://github.com/claridgicus/how-many-tokens-left"
license=('MIT')
depends=('python>=3.11')
optdepends=('waybar: status bar integration'
            'python-gobject: dropdown panel'
            'gtk4: dropdown panel'
            'gtk4-layer-shell: dropdown panel'
            'xdg-utils: middle-click opens the quota dashboard')
source=()
sha256sums=()

check() {
  cd "$startdir"
  python -m unittest discover -s tests
}

package() {
  cd "$startdir"
  make DESTDIR="$pkgdir" PREFIX=/usr install
}
