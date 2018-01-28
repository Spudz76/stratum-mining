import time
from twisted.internet import reactor, defer, endpoints
from twisted.internet.error import ConnectionRefusedError

import custom_exceptions
from protocol import Protocol, ClientProtocol
from stratum.event_handler import GenericEventHandler


from lib.sia_rpc_manager import SiaRPCManager

import logger
log = logger.get_logger('sia_rpc_poller')

def _refusedHandler(e):
    log.error('Connection problem (are your COIND_* settings correct?)')
    log.error('Exception: %s' % str(e))
    reactor.stop()

class SiaRPCPoller(GenericEventHandler):
    def __init__(self, debug=False, event_handler=GenericEventHandler):
        self.rpc = SiaRPCManager()
        self.debug = debug
        self.event_handler = event_handler
        self.pollClock = None # Reference to reactor.callLater instance
        self.blockheight = 0
        self.on_disconnect = defer.Deferred()
        self.on_connect = defer.Deferred()
        self.connect()

    def connect(self):
        self.pollClock = None
        log.info('Connecting to siad...')
        while True:
            try:
                result = (yield self.rpc.check_ready())
                if not result:
                    log.error('SiaD downloading blockchain... will check back in 5 sec')
                    time.sleep(4)
            except ConnectionRefusedError, e:
                (yield _refusedHandler(e))
                break
            except Exception, e:
                log.debug(str(e))
            time.sleep(1)  # If we didn't get a result or the connect failed
        log.info('SiaD responding and available, begin polling')
        self.pollClock = reactor.callLater(1, self.get_consensus)

    def reconnect(self):
        (yield self.connect())

    def get_consensus(self):
        self.pollClock = None
        try:
            consensus = (yield self.rpc.get_consensus())
            if not consensus['synced']:
                log.error('SiaD poll failed, switching back to poll-for-ready')
                self.connect()
            else:
                if self.blockheight < consensus['height']:
                    self.blockheight = consensus['height']
                    (yield self.newBlock())
        except ConnectionRefusedError, e:
            (yield _refusedHandler(e))
            break
        except Exception, e:
            log.debug(str(e))
        self.pollClock = reactor.callLater(1, self.get_consensus)

    def get_work(self):
        try:
            work = (yield self.rpc.get_work())
            if not work:
                log.error('SiaD poll failed, switching back to poll-for-ready')
                self.connect()
            else:
                if self.blockheight < consensus['height']:
                    self.blockheight = consensus['height']
                    (yield self.newBlock())
        except ConnectionRefusedError, e:
            (yield _refusedHandler(e))
            break
        except Exception, e:
            log.debug(str(e))

    def newBlock(self):

        self.event_handler.handle_event('mining.notify',[
            job_id,
            prevhash,
            coinb1,
            coinb2,
            merkle_branch,
            version,
            nbits,
            ntime,
            clean_jobs
        ])
