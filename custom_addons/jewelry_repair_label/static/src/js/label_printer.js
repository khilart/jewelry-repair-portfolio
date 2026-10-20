/** @odoo-module **/

/**
 * Web Serial transport for the label printer.
 *
 * The printer is reached over a Bluetooth serial port: on Windows the pairing
 * creates a COM port, on macOS a /dev/cu.* device. The browser grants access to
 * one port per origin, so the operator picks it once and it is remembered.
 *
 * The printer drops the link when a whole label is pushed in one burst, so the
 * stream is written in small chunks with a pause between them.
 */

const BAUD_RATE = 115200;
const CHUNK_SIZE = 128;
const CHUNK_PAUSE_MS = 20;

export function isSerialSupported() {
    return typeof navigator !== "undefined" && "serial" in navigator;
}

/** Port the operator has already granted, or null. */
export async function grantedPort() {
    if (!isSerialSupported()) {
        return null;
    }
    const ports = await navigator.serial.getPorts();
    return ports.length ? ports[0] : null;
}

/** Opens the browser picker. Must be called from a user gesture. */
export async function pickPort() {
    return navigator.serial.requestPort();
}

export async function forgetPort() {
    const port = await grantedPort();
    if (port && port.forget) {
        await port.forget();
    }
}

/** Writes a ready made printer program to the port. */
export async function sendToPrinter(bytes) {
    const port = (await grantedPort()) || (await pickPort());
    await port.open({ baudRate: BAUD_RATE });
    const writer = port.writable.getWriter();
    try {
        for (let at = 0; at < bytes.length; at += CHUNK_SIZE) {
            await writer.write(bytes.slice(at, at + CHUNK_SIZE));
            await new Promise((resolve) => setTimeout(resolve, CHUNK_PAUSE_MS));
        }
    } finally {
        writer.releaseLock();
        await port.close();
    }
}
