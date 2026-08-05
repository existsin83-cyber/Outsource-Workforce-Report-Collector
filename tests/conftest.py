import os

# Qt dialog tests create and show real top-level windows. Running the full
# suite on a real display lets those windows fight over OS-level keyboard
# focus, which makes QTest.keyClick assertions flaky depending on run order.
# The offscreen platform plugin sidesteps that entirely.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
