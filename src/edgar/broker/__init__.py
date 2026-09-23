# edgar.broker is v4, and removable: nothing in Core, v1, v2 or v3 imports it, a
# test proves it, and CI deletes the package and runs the suite below it [NFR-12].
# attach() lands with the receipt subscriber and the pre_tool veto wiring, still
# to be built [ADR-0039]; only the pure core (caveats, ticket, authorize) exists
# so far, so this package has no entry point yet.
