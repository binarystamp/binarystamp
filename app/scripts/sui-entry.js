// Bundle entry for the browser-side Sui SDK.
// Built into frontend/vendor/sui.js by `./_start build` (see package.json).
// Keeping the bundle local means the app loads no external resources at runtime.

export { Transaction } from '@mysten/sui/transactions';
export { SuiJsonRpcClient, getJsonRpcFullnodeUrl } from '@mysten/sui/jsonRpc';
export {
    SUI_CLOCK_OBJECT_ID,
    fromBase64,
    toBase64,
    isValidSuiAddress,
    normalizeSuiAddress,
} from '@mysten/sui/utils';
