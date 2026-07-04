"""GEX / call wall / put wall computation — the dealer-sign assumption lives here.

STATUS: stub for M2. Not implemented at M0. No invented formula ships here until
it is verified against IBKR model greeks and sanity-checked (§8/§13).

Computation contract (§8), to be implemented:
  * Per-strike gamma exposure aggregated across the chain by strike, scaled by
    contract multiplier and open interest, under the *configurable* dealer-sign
    convention (settings.dealer_sign_convention, §6.1).
  * Call wall / put wall = derived strike levels of extreme aggregated gamma,
    emitted as labeled price levels carrying the assumption marker.
  * The GEX profile (gamma by strike) is a distinct artifact from net GEX over
    time; keep them clearly named and separate.
  * Every computed snapshot is pinned to its source option_chain_snapshot id and
    capture timestamp so it is reproducible and point-in-time (§6.2/§6.3).

Any value produced here is assumption-dependent, never a measured fact. Do not
add language that asserts dealer intent as known.
"""
