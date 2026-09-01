# PR 1: Session Persistence Fix

## Title
Fix session persistence: JSON instead of dead pickle calls

## Base
copilot/build-secure-authentication-system

## Compare
claude/fix-login-manager-session-persistence

## Body

save_session() and load_session() called pickle.dump/pickle.load but the module never imported pickle, so both raised NameError on first use. The branch's own test (TestSessionPersistence::test_save_and_load) fails on the unfixed code: `pytest tests/` is 1 failed, 16 passed. It is now 17 passed.

Serialise as JSON rather than adding the missing pickle import. Two reasons, the second one is the real one:

1. The rest of the module already assumed JSON — get_user_session_path() returns a .json path and list_saved_sessions() globs *.json. The pickle calls were the outlier, not the docstring.
2. pickle.load on a predictable path under $HOME executes whatever the file says. JSON removes that class of problem outright. Only the cookie fields needed to rebuild the jar are stored.

Also fixed, found while reproducing: save_session() left a 0-byte file at mode 644. path.open("wb") created it, pickle.dump raised, and the path.chmod(0o600) two lines later never ran — so the docstring's "mode 0600 so only the current OS user can read it" was not delivered on the failure path. The file is now created 0600 via os.open() instead of being chmod-ed after the write.

A session file written by an older build is not valid JSON, so it is rejected gracefully and a fresh login runs. A version field guards the format going forward.

Verified by running the real functions: save -> load round-trip through a live local HTTP server so is_authenticated()'s probe genuinely executes; cookies come back identical, file is 384 bytes at mode 600.
