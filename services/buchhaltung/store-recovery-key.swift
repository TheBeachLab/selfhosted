// Store the document key in the Mac login Keychain without argv, files or logs.
// Never overwrite a pre-existing entry with a different key.
import Foundation
import Security

let supplied = FileHandle.standardInput.readDataToEndOfFile()
guard let text = String(data: supplied, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
      let key = Data(base64Encoded: text), key.count == 32 else {
    fputs("Invalid encryption key input.\n", stderr); exit(1)
}
let query: [String: Any] = [
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: "buchhaltung.beachlab.org.document-encryption",
    kSecAttrAccount as String: "fran",
    kSecAttrSynchronizable as String: false
]
var read = query
read[kSecReturnData as String] = true
read[kSecMatchLimit as String] = kSecMatchLimitOne
var existing: CFTypeRef?
let found = SecItemCopyMatching(read as CFDictionary, &existing)
if found == errSecSuccess {
    guard let value = existing as? Data, value == key else {
        fputs("A different recovery key already exists; no replacement made.\n", stderr); exit(2)
    }
    print("Recovery key already matches the NUC key.")
} else if found == errSecItemNotFound {
    var entry = query
    entry[kSecAttrLabel as String] = "Beach Lab Buchhaltung · recovery encryption key"
    entry[kSecValueData as String] = key
    let saved = SecItemAdd(entry as CFDictionary, nil)
    guard saved == errSecSuccess else {
        fputs("Keychain storage failed (\(saved)).\n", stderr); exit(3)
    }
    print("Recovery encryption key saved in the Mac login Keychain.")
} else {
    fputs("Keychain query failed (\(found)).\n", stderr); exit(4)
}
