# CreateFromCSV — UserForm for CorelDRAW 2026

This version uses the exact binary FRX exported from CorelDRAW 2026 by the user, with an FRM header based on that export.

## Install
1. Run Синхронизация.bat to retrieve both files.
2. In VBA, remove any old **module** or form named `frmCreateFromCSV`.
3. Keep `frmCreateFromCSV.frm` and `frmCreateFromCSV.frx` together in the same folder.
4. In the intended GMS project use File → Import File and select `frmCreateFromCSV.frm`.
5. Verify it appears under **Forms**, not Modules. Save the GMS.
6. Launch the form via your existing CreateFromCSV module.

## Important implementation detail
- The FRX is **unchanged**, taken from the real CorelDRAW export. The FRM uses the genuine Microsoft Forms class GUID.
- Controls are created at **form runtime** using `Me.Controls.Add` and wired with `WithEvents`. They will appear **when the form is opened**, not in the VBA designer.
- This avoids changing the opaque MSForms binary structure without CorelDRAW. It does not require enabling access to the VBA project object model.
- The form references `ChooseCSV(ActiveDocument)`, `CreateCSVTemplate()`, and `RunCreateFromCSV(path, columns, x, y)`. These procedures must exist in your existing `CreateFromCSV` module with compatible signatures. The earlier GUI module may differ and has not been verified.
- This pair has been assembled and checked in GitHub, **but not tested inside CorelDRAW 2026**. If import fails, please provide the exact error.
- The previous installer `InstallCreateFromCSVForm.bas` is obsolete; do not run it.
