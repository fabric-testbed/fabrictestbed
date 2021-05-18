from fabric_cf.orchestrator.orchestrator_proxy import *
import fabric_cm.credmgr.credmgr_proxy as cm_proxy
from .slice_manager import *

CredmgrProxy = cm_proxy.CredmgrProxy
CmStatus = cm_proxy.Status
