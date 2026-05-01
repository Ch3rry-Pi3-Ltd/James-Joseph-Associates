"""
Resume text-extraction helpers.

This module is the next stage after transient CV download.

Why this module exists
----------------------
By this point in the JobAdder pipeline, the backend can already:

- fetch candidate detail
- fetch candidate attachments
- identify the latest likely resume
- download the selected attachment bytes
"""