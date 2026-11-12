You grade a commitment extractor against a human answer key for one meeting.

Gold items (G*) were written by a human annotator as the meeting's action items. Predicted items (P*) came from a system that heard the meeting through speech recognition.

A predicted item MATCHES a gold item when it describes the same future task for the same role or group. Different wording, a more specific version, or one predicted item that covers part of a gold item all count as a match. A different task, a past action, or a general idea does not.

Return, for every gold item, the ids of the predicted items that match it (empty list if none). Judge only what is written.
