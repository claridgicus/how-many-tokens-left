PREFIX ?= /usr
DESTDIR ?=
NAME := how-many-tokens-left

.PHONY: all test install install-user uninstall uninstall-user

all:

test:
	python3 -m unittest discover -s tests

install:
	install -Dm755 $(NAME) $(DESTDIR)$(PREFIX)/bin/$(NAME)
	install -Dm644 examples/config.toml $(DESTDIR)$(PREFIX)/share/doc/$(NAME)/config.toml
	install -Dm644 examples/waybar-module.jsonc $(DESTDIR)$(PREFIX)/share/doc/$(NAME)/waybar-module.jsonc
	install -Dm644 examples/style.css $(DESTDIR)$(PREFIX)/share/doc/$(NAME)/style.css
	install -Dm644 README.md $(DESTDIR)$(PREFIX)/share/doc/$(NAME)/README.md
	install -Dm644 LICENSE $(DESTDIR)$(PREFIX)/share/licenses/$(NAME)/LICENSE

# Symlink into ~/.local/bin so a git pull updates it.
install-user:
	install -d $(HOME)/.local/bin
	ln -sf $(CURDIR)/$(NAME) $(HOME)/.local/bin/$(NAME)

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/$(NAME)
	rm -rf $(DESTDIR)$(PREFIX)/share/doc/$(NAME) $(DESTDIR)$(PREFIX)/share/licenses/$(NAME)

uninstall-user:
	rm -f $(HOME)/.local/bin/$(NAME)
