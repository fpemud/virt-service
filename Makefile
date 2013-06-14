PACKAGE_VERSION = `/bin/fgrep GK_V= genkernel | sed "s/.*GK_V='\([^']\+\)'/\1/"`
distdir = virt-service-$(PACKAGE_VERSION)
prefix=/usr

PROGRAMS := virt-service-daemon

all: $(PROGRAMS)

clean:
	find . -name *.pyc | xargs rm -f
	rm -rf virt-service-daemon

check-git-repository:
	git diff --quiet || { echo 'STOP, you have uncommitted changes in the working directory' ; false ; }
	git diff --cached --quiet || { echo 'STOP, you have uncommitted changes in the index' ; false ; }

dist: check-git-repository distclean
	mkdir "$(distdir)"
	git ls-files -z | xargs -0 cp --no-dereference --parents --target-directory="$(distdir)" 
	tar cf "$(distdir)".tar "$(distdir)"
	bzip2 -9v "$(distdir)".tar
	rm -Rf "$(distdir)"

distclean:
	rm -Rf "$(distdir)" "$(distdir)".tar "$(distdir)".tar.bz2

install: $(PROGRAMS)
	install -d -m 0755 "$(DESTDIR)/$(prefix)/share/dbus-1/services"
	install -m 0644 data/virt-service.service "$(DESTDIR)/$(prefix)/share/dbus-1/services"

	install -d -m 0755 "$(DESTDIR)/$(prefix)/libexec/virt-service"
	cp -r src/* "$(DESTDIR)/$(prefix)/libexec/virt-service"
	find "$(DESTDIR)/$(prefix)/libexec/virt-service" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/libexec/virt-service" -type d | xargs chmod 755
	install -m 4755 virt-service-daemon "$(DESTDIR)/$(prefix)/libexec/virt-service"

#	install -d -m 0755 "$(DESTDIR)/etc/xdg/menus"
#	cp desktop/*.menu "$(DESTDIR)/etc/xdg/menus"
#	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib/desktop-directories"
#	cp desktop/*.directory "$(DESTDIR)/$(prefix)/lib/desktop-directories"

uninstall:
	rm -Rf "$(DESTDIR)/$(prefix)/share/dbus-1/services/virt-service.service"
	rm -Rf "$(DESTDIR)/$(prefix)/libexec/virt-service"

virt-service-daemon:
	$(CC) $(CFLAGS) $(LDFLAGS) virt-service-daemon.c -o virt-service-daemon

.PHONY: check-git-repository all clean dist distclean install uninstall

