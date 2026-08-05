// Backend endpoint and request bounds for the Ritaj Assistant.
//
// If the backend ever moves to a custom domain, change BASE_URL here AND the
// matching entry in manifest.json "host_permissions", then bump the version and
// re-publish.
const BASE_URL = 'https://mohawwad04-ritaj-rag.hf.space'

// Longest message the backend will accept. Duplicated from the server's
// MAX_MESSAGE_CHARS so the panel can refuse locally with a sentence a student
// understands, instead of sending a request that comes back as a 422 the UI
// would have to translate.
//
// Duplication is checked, not trusted: scripts/check_extension.py fails the
// build if this drifts from ritaj.config.settings.max_message_chars. There used
// to be three different answers to this question and no check at all.
const MAX_MESSAGE_CHARS = 2000
