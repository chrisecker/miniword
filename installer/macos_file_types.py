"""
Adds the file types to the Info.plist of the MiniWord.app built by
PyInstaller: .txl (MiniWord's own), .md and plain text.

    python installer/macos_file_types.py dist/MiniWord.app
"""

import plistlib
import sys

TXL = 'org.codeberg.chrisecker.miniword.txl'
MD = 'net.daringfireball.markdown'  # the usual type of Markdown


def text_type(uti, description, extensions):
    return {'UTTypeIdentifier': uti, 'UTTypeDescription': description,
            'UTTypeConformsTo': ['public.plain-text'],
            'UTTypeTagSpecification': {
                'public.filename-extension': extensions}}


def main(app):
    path = app + '/Contents/Info.plist'
    with open(path, 'rb') as f:
        plist = plistlib.load(f)
    plist['CFBundleDocumentTypes'] = [
        {'CFBundleTypeName': 'MiniWord Document',
         'CFBundleTypeRole': 'Editor', 'LSHandlerRank': 'Owner',
         'LSItemContentTypes': [TXL],
         'CFBundleTypeIconFile': plist.get('CFBundleIconFile', '')},
        {'CFBundleTypeName': 'Markdown Document',
         'CFBundleTypeRole': 'Editor', 'LSHandlerRank': 'Default',
         'LSItemContentTypes': [MD]},
        {'CFBundleTypeName': 'Text Document',
         'CFBundleTypeRole': 'Editor', 'LSHandlerRank': 'Alternate',
         'LSItemContentTypes': ['public.plain-text']},
    ]
    plist['UTExportedTypeDeclarations'] = [
        text_type(TXL, 'MiniWord Document', ['txl'])]
    plist['UTImportedTypeDeclarations'] = [
        text_type(MD, 'Markdown Document', ['md', 'markdown'])]
    with open(path, 'wb') as f:
        plistlib.dump(plist, f)


if __name__ == '__main__':
    main(sys.argv[1])
