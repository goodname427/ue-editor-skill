'use strict';
const vm = require('vm');
globalThis.fixture = {
    count: 7,
    big: 9007199254740993n,
    missing: undefined,
    nil: null,
    text: '中文'.repeat(600),
    arr: [11, 22, 33, 44],
    sparse: [1, , 3],
    nested: { name: 'expected' },
    calls: 0,
    map: new Map([['key', 123]]),
    proxy: new Proxy({ hidden: 123 }, { ownKeys() { fixture.calls++; return ['hidden']; } })
};
fixture.self = fixture;
Object.defineProperty(fixture, 'danger', {
    enumerable: true,
    get() { fixture.calls++; return 99; }
});
if (process.argv.includes('--multi-context')) {
    vm.runInContext('globalThis.fixture = { count: 999 }', vm.createContext({}, { name: 'second-context' }));
}
console.log('fixture-ready');
setInterval(() => {}, 1000);
