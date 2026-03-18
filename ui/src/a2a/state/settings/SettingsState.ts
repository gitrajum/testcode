// SettingsState: Settings State.
export class SettingsState {
    output_mime_types: string[] = ["image/*", "text/plain"];

    // Arize Phoenix settings
    arize_phoenix_url: string = "";
    arize_phoenix_enabled: boolean = false;

    constructor(init?: Partial<SettingsState>) {
        if (init) {
            Object.assign(this, init);
        }
    }
}
