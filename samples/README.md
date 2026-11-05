# Sample inputs

`sample_inputs.json` lists demo captions (English and Arabic) and which file to attach. The image
`demo_smoke_skyline.jpg` and clip `demo_pan.mp4` were **drawn programmatically** for demonstration
(see `README.md` > Demo); they are not photographs of a real event. Because the image is synthetic,
the AI-generated-media signal may or may not fire on it, which is itself a useful demonstration
that the signal is qualified.

`example_reports/` contains HTML and JSON reports produced by running these inputs through the
application (`python -I scripts/make_examples.py`). They are real outputs of this version of the
system, not mock results.
