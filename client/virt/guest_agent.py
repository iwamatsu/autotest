"""
Interfaces to the virt agent.

@copyright: 2008-2012 Red Hat Inc.
"""

import socket, time, logging
from kvm_monitor import Monitor, MonitorError

try:
    import json
except ImportError:
    logging.warning("Could not import json module. "
                    "virt agent functionality disabled.")


class VAgentError(MonitorError):
    def __init__(self):
        MonitorError.__init__(self)


class VAgentConnectError(VAgentError):
    pass


class VAgentSocketError(VAgentError):
    def __init__(self, msg, e):
        VAgentError.__init__(self, msg, e)
        self.msg = msg
        self.e = e

    def __str__(self):
        return "%s    (%s)" % (self.msg, self.e)


class VAgentLockError(VAgentError):
    pass


class VAgentProtocolError(VAgentError):
    pass


class VAgentNotSupportedError(VAgentError):
    pass


class VAgentCmdError(VAgentError):
    def __init__(self, cmd, args, data):
        VAgentError.__init__(self, cmd, args, data)
        self.cmd = cmd
        self.args = args
        self.data = data

    def __str__(self):
        return ("Virt Agent command %r failed    (arguments: %r,    "
                "error message: %r)" % (self.cmd, self.args, self.data))


class QemuAgent(Monitor):
    """
    Wraps qemu guest agent commands.
    """

    READ_OBJECTS_TIMEOUT = 5
    CMD_TIMEOUT = 20
    RESPONSE_TIMEOUT = 20
    PROMPT_TIMEOUT = 20

    def __init__(self, vm, name="org.qemu.guest_agent.0", filename=None,
                 get_supported_cmds=False, suppress_exceptions=False):
        """
        Connect to the guest agent socket, Also make sure the json
        module is available.

        @param vm: The VM object who has this GuestAgent.
        @param name: Guest agent identifier.
        @param filename: Guest agent socket filename.
        @param get_supported_cmds: Try to get supported cmd list when initiation.
        @param suppress_exceptions: If True, ignore VAgentError exception.

        @raise VAgentConnectError: Raised if the connection fails and
                suppress_exceptions is False
        @raise VAgentProtocolError: Raised if the no QMP greeting message is
                received and suppress_exceptions is False
        @raise VAgentNotSupportedError: Raised if json isn't available and
                suppress_exceptions is False
        """
        try:
            if not filename:
                filename = vm.get_virtio_port_filename(name)

            Monitor.__init__(self, name, filename)
            # Make sure json is available
            try:
                json
            except NameError:
                raise VAgentNotSupportedError("guest agent requires the json"
                                              " module (Python 2.6 and up)")

            # Set a reference to the VM object that has this GuestAgent.
            self.vm = vm

            if get_supported_cmds:
                self._get_supported_cmds()

        except VAgentError, e:
            self._close_sock()
            if suppress_exceptions:
                logging.warn(e)
            else:
                raise


    # Methods only used inside this class

    def _build_cmd(self, cmd, args=None):
        obj = {"execute": cmd}
        if args is not None:
            obj["arguments"] = args
        return obj


    def _read_objects(self, timeout=READ_OBJECTS_TIMEOUT):
        """
        Read lines from the guest agent socket and try to decode them.
        Stop when all available lines have been successfully decoded, or when
        timeout expires. Return all decoded objects.

        @param timeout: Time to wait for all lines to decode successfully
        @return: A list of objects
        """
        if not self._data_available():
            return []
        s = ""
        end_time = time.time() + timeout
        while self._data_available(end_time - time.time()):
            s += self._recvall()
            # Make sure all lines are decodable
            for line in s.splitlines():
                if line:
                    try:
                        json.loads(line)
                    except Exception:
                        # Found an incomplete or broken line -- keep reading
                        break
            else:
                # All lines are OK -- stop reading
                break
        # Decode all decodable lines
        objs = []
        for line in s.splitlines():
            try:
                objs += [json.loads(line)]
                self._log_lines(line)
            except Exception:
                pass
        return objs


    def _send(self, data):
        """
        Send raw data without waiting for response.

        @param data: Data to send
        @raise VAgentSocketError: Raised if a socket error occurs
        """
        try:
            self._socket.sendall(data)
            self._log_lines(str(data))
        except socket.error, e:
            raise VAgentSocketError("Could not send data: %r" % data, e)


    def _get_response(self, timeout=RESPONSE_TIMEOUT):
        """
        Read a response from the guest agent socket.

        @param id: If not None, look for a response with this id
        @param timeout: Time duration to wait for response
        @return: The response dict
        """
        end_time = time.time() + timeout
        while self._data_available(end_time - time.time()):
            for obj in self._read_objects():
                if isinstance(obj, dict):
                    if "return" in obj or "error" in obj:
                        return obj
        # Return empty dict when timeout.
        return {}


    def _get_supported_cmds(self):
        """
        Get supported qmp cmds list.
        """
        cmds = self.cmd("guest-info", debug=False)
        if cmds and cmds.has_key("supported_commands"):
            cmd_list = cmds["supported_commands"]
            self._supported_cmds = [n["name"] for n in cmd_list if
                                    isinstance(n, dict) and n.has_key("name")]

        if not self._supported_cmds:
            # If initiation fails, set supported list to a None-only list.
            self._supported_cmds = [None]
            logging.warn("Could not get supported guest agent cmds list")


    def _has_command(self, cmd):
        """
        Check wheter guest agent support 'cmd'.

        @param cmd: command string which will be checked.

        @return: True if cmd is supported, False if not supported.
        """
        # Initiate supported cmds list if it's empty.
        if not self._supported_cmds:
            self.get_supported_cmds()

        # If the first element in supported cmd list is 'None', it means
        # autotest fails to get the cmd list, so bypass cmd checking.
        if self._supported_cmds[0] is None:
            return True

        if cmd and cmd in self._supported_cmds:
            return True
        return False


    def _log_command(self, cmd, debug=True, extra_str=""):
        """
        Print log message beening sent.

        @param cmd: Command string.
        @param debug: Whether to print the commands.
        @param extra_str: Extra string would be printed in log.
        """
        if self.debug_log or debug:
            logging.debug("(vagent %s) Sending command '%s' %s",
                          self.name, cmd, extra_str)


    def _log_response(self, cmd, resp, debug=True):
        """
        Print log message for guest agent cmd's response.

        @param cmd: Command string.
        @param resp: Response from guest agent command.
        @param debug: Whether to print the commands.
        """
        def _log_output(o, indent=0):
            logging.debug("(vagent %s)    %s%s",
                          self.name, " " * indent, o)

        def _dump_list(li, indent=0):
            for l in li:
                if isinstance(l, dict):
                    _dump_dict(l, indent + 2)
                else:
                    _log_output(str(l), indent)

        def _dump_dict(di, indent=0):
            for k, v in di.iteritems():
                o = "%s%s: " % (" " * indent, k)
                if isinstance(v, dict):
                    _log_output(o, indent)
                    _dump_dict(v, indent + 2)
                elif isinstance(v, list):
                    _log_output(o, indent)
                    _dump_list(v, indent + 2)
                else:
                    o += str(v)
                    _log_output(o, indent)

        if self.debug_log or debug:
            logging.debug("(vagent %s) Response to '%s' "
                          "(re-formated)", self.name, cmd)
            if isinstance(resp, dict):
                _dump_dict(resp)
            elif isinstance(resp, list):
                _dump_list(resp)
            else:
                for l in str(resp).splitlines():
                    _log_output(l)


    # Public methods

    def cmd(self, cmd, args=None, timeout=CMD_TIMEOUT, debug=True,
            success_resp=True):
        """
        Send a guest agent command and return the response if success_resp is
        True.

        @param cmd: Command to send
        @param args: A dict containing command arguments, or None
        @param timeout: Time duration to wait for response
        @param debug: Whether to print the commands being sent and responses
        @param fd: file object or file descriptor to pass

        @return: The response received

        @raise VAgentLockError: Raised if the lock cannot be acquired
        @raise VAgentSocketError: Raised if a socket error occurs
        @raise VAgentProtocolError: Raised if no response is received
        @raise VAgentCmdError: Raised if the response is an error message
                               (the exception's args are (cmd, args, data)
                                where data is the error data)
        """
        self._log_command(cmd, debug)
        # Send command
        cmdobj = self._build_cmd(cmd, args)
        data = json.dumps(cmdobj) + "\n"
        r = self.cmd_raw(data, timeout, success_resp)

        if not success_resp:
            return ""

        if "return" in r:
            ret = r["return"]
            if ret:
                self._log_response(cmd, ret, debug)
            return ret
        if "error" in r:
            raise VAgentCmdError(cmd, args, r["error"])



    def cmd_raw(self, data, timeout=CMD_TIMEOUT, success_resp=True):
        """
        Send a raw string to the guest agent and return the response.
        Unlike cmd(), return the raw response dict without performing
        any checks on it.

        @param data: The data to send
        @param timeout: Time duration to wait for response
        @return: The response received
        @raise VAgentLockError: Raised if the lock cannot be acquired
        @raise VAgentSocketError: Raised if a socket error occurs
        @raise VAgentProtocolError: Raised if no response is received
        """
        if not self._acquire_lock():
            raise VAgentLockError("Could not acquire exclusive lock to send "
                                  "data: %r" % data)

        try:
            self._read_objects()
            self._send(data)
            # Return directly for some cmd without any response.
            if not success_resp:
                return {}

            # Read response
            r = self._get_response(timeout)

        finally:
            self._lock.release()

        if r is None:
            raise VAgentProtocolError("Received no response to data: %r" % data)
        return r


    def cmd_obj(self, obj, timeout=CMD_TIMEOUT):
        """
        Transform a Python object to JSON, send the resulting string to
        the guest agent, and return the response.
        Unlike cmd(), return the raw response dict without performing any
        checks on it.

        @param obj: The object to send
        @param timeout: Time duration to wait for response
        @return: The response received
        @raise VAgentLockError: Raised if the lock cannot be acquired
        @raise VAgentSocketError: Raised if a socket error occurs
        @raise VAgentProtocolError: Raised if no response is received
        """
        return self.cmd_raw(json.dumps(obj) + "\n", timeout)


    def verify_responsive(self):
        """
        Make sure the guest agent is responsive by sending a command.
        """
        cmd = "guest-ping"
        if self._has_command(cmd):
            self.cmd(cmd=cmd, debug=False)


    def shutdown(self):
        """
        Send "guest-shutdown", this cmd would not return any response.
        """
        cmd = "guest-shutdown"
        if self._has_command(cmd):
            self.cmd(cmd=cmd, success_resp=False)
