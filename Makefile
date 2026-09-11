.PHONY: start stop status test bootstrap
bootstrap:
	./scripts/bootstrap.sh
start:
	ddev start
stop:
	ddev stop
status:
	ddev platform-status
test:
	ddev platform-test
