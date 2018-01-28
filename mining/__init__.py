from service import MiningService
from subscription import MiningSubscription
from twisted.internet import defer
from twisted.internet.error import ConnectionRefusedError
import time
import simplejson as json
from twisted.internet import reactor
import threading
from mining.work_log_pruner import WorkLogPruner

@defer.inlineCallbacks
def setup(on_startup):
    '''Setup mining service internal environment.
    You should not need to change this. If you
    want to use another Worker manager or Share manager,
    you should set proper reference to Interfaces class
    *before* you call setup() in the launcher script.'''

    import lib.settings as settings

    # Get logging online as soon as possible
    import lib.logger
    log = lib.logger.get_logger('mining')
    if settings.CONFIG_VERSION == None:
        settings.CONFIG_VERSION = 0
    else: pass
    from interfaces import Interfaces

    from mining_libs import client_service
    from mining_libs import jobs
    from mining_libs import worker_registry
    from mining_libs import utils

    from lib.block_updater import BlockUpdater
    from lib.template_registry import TemplateRegistry
    from lib.sia_rpc_manager import SiaRPCManager
    from lib.block_template import BlockTemplate
    from lib.coinbaser import SimpleCoinbaser

    sia_rpc = SiaRPCManager()

    def _refusedHandler(e):
        log.error('Connection problem (are your COIND_* settings correct?)')
        log.error('Exception: %s' % str(e))
        reactor.stop()

    # Check coind
    #         Check we can connect (sleep)
    # Check the results:
    #         - getblocktemplate is avalible        (Die if not)
    #         - we are not still downloading the blockchain        (Sleep)
    log.info('Connecting to siad...')
    while True:
        try:
            result = (yield sia_rpc.check_ready())
            if not result:
                log.error('SiaD downloading blockchain... will check back in 5 sec')
                time.sleep(4)
        except ConnectionRefusedError, e:
            (yield _refusedHandler(e))
            break
        except Exception, e:
            log.debug(str(e))
        time.sleep(1)  # If we didn't get a result or the connect failed

    log.info('Connected to the coind - Begining to load Address and Module Checks!')
    # Start the coinbaser
    coinbaser = SimpleCoinbaser(sia_rpc, getattr(settings, 'CENTRAL_WALLET'))
    (yield coinbaser.on_load)

    # Connect to Sia Daemon via Factory
    f = SocketTransportClientFactory(args.host, args.port,
                                     debug=args.verbose, proxy=proxy,
                                     event_handler=client_service.ClientMiningService)

    job_registry = jobs.JobRegistry(f, cmd=args.blocknotify_cmd)
    client_service.ClientMiningService.job_registry = job_registry
    client_service.ClientMiningService.reset_timeout()

    workers = worker_registry.WorkerRegistry(f)
    f.on_connect.addCallback(on_connect, workers, job_registry)
    f.on_disconnect.addCallback(on_disconnect, workers, job_registry)

    registry = TemplateRegistry(BlockTemplate,
                                coinbaser,
                                sia_rpc,
                                getattr(settings, 'INSTANCE_ID'),
                                MiningSubscription.on_template,
                                Interfaces.share_manager.on_network_block)

    # Template registry is the main interface between Stratum service
    # and pool core logic
    Interfaces.set_template_registry(job_registry)

    # Set up polling mechanism for detecting new block on the network
    # This is just failsafe solution when -blocknotify
    # mechanism is not working properly
    BlockUpdater(job_registry, sia_rpc)

    prune_thr = threading.Thread(target=WorkLogPruner, args=(Interfaces.worker_manager.job_log,))
    prune_thr.daemon = True
    prune_thr.start()

    log.info('MINING SERVICE IS READY')
    on_startup.callback(True)
