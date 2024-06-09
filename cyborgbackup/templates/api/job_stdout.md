# Retrieve {{ model_verbose_name|title }} Stdout:

Make GET request to this resource to retrieve the stdout from running this
{{ model_verbose_name }}.

## Format

Use the `format` query string parameter to specify the output format.

* Browsable API: `?format=api`
* HTML: `?format=html`
* Plain Text: `?format=txt`
* Plain Text with ANSI color codes: `?format=ansi`
* JSON structure: `?format=json`
* Downloaded Plain Text: `?format=txt_download`
* Downloaded Plain Text with ANSI color codes: `?format=ansi_download`

Files over {{ settings.STDOUT_MAX_BYTES_DISPLAY|filesizeformat }} (configurable)
will not display in the browser. Use the `txt_download` or `ansi_download`
formats to download the file directly to view it.
