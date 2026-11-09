// Campaign environment guard: allow only explicit loopback TCP connections.
const net = require('node:net');
const dns = require('node:dns');
const cp = require('node:child_process');
const local = host => host === undefined || host === '127.0.0.1' || host === 'localhost';
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  const options = typeof args[0] === 'object' ? args[0] : {host: typeof args[1] === 'string' ? args[1] : undefined};
  if (!options.path && !local(options.host)) throw new Error('Black-box campaign blocked non-local socket');
  return connect.apply(this, args);
};
const lookup = dns.lookup;
dns.lookup = function(host, ...args) {
  if (!local(host)) throw new Error('Black-box campaign blocked non-local DNS');
  return lookup.call(this, host, ...args);
};
const spawn = cp.spawn;
cp.spawn = function(command, args, options = {}) {
  const env = {...(options.env || process.env), NODE_OPTIONS: '--require=' + JSON.stringify(__filename)};
  return spawn.call(this, command, args, {...options, env});
};
