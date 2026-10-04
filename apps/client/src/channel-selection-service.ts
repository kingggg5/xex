import { createChannelSelectionCore } from "./connection-service.mjs";
import { parseRooms, saveStoredChannel } from "./rooms-ui";

export { ChannelSelectionError } from "./connection-service.mjs";
export type {
	ChannelSelectionService,
	ChannelLoadResult,
	ChannelRoom,
	ChannelSelectionErrorCode,
} from "./connection-service.mjs";

/** Real session requests; the lobby owns display, selection and reconnecting. */
export function createChannelSelectionService(options: { worldName: string }) {
	return createChannelSelectionCore({
		worldName: options.worldName,
		fetchImpl: (input, init) => fetch(input, init),
		parseRooms,
		saveStoredChannel,
	});
}
