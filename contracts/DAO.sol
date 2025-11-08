// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "./DataTypes.sol";
import "./Requester.sol";
import "./Trainer.sol";
import "./JobContract.sol";

event OfferMade(uint256 indexed offerId, address indexed requester, address indexed trainer);
event JobContractCreated(address indexed job, uint256 indexed offerId, address indexed requester, address trainer);

contract DAO {
    using Counters for Counters.Counter;

    mapping(address => address) public trainers;
    address[] public registeredTrainers;

    mapping(address => address) public requesters;
    address[] public registeredRequesters;

    mapping(address => JobContract) jobContracts;

    Counters.Counter UID;

    function nextID() private returns(uint256) {
       uint256 ID = UID.current();
       UID.increment();
       return ID;
    }

    function registerTrainer (string memory _description, DataTypes.Specification memory _specification ) external returns(address){
        require(
            !isTrainer(msg.sender), "Trainer already registered"
        );
        Trainer newTrainer = new Trainer(payable(msg.sender), _description, _specification);
        trainers[msg.sender] =  address(newTrainer);
        registeredTrainers.push(msg.sender);
        return address(newTrainer);
    }

    function registerRequester ( ) external returns(address){
        require(
            !isRequester(msg.sender), "Requester already registered"
        );
        Requester newRequester = new Requester(payable(msg.sender));
        requesters[msg.sender] =  address(newRequester);
        registeredRequesters.push(msg.sender);
        return address(newRequester);
    }

    function matchTrainers (DataTypes.JobRequirements memory Requirements) external view returns(address  [] memory) {
        address [] memory candidates = new address[](Requirements.canditatesToReturn);
        uint256 candidatesCount = 0;
        uint256 i = 0;

        while ((candidatesCount < Requirements.canditatesToReturn) && (i < registeredTrainers.length)) {
            address trainerAddr = registeredTrainers[i];

            // --- INÍCIO DA CORREÇÃO HHE910 ---
            // Convertemos o 'address' para 'payable' antes de converter para o tipo 'Trainer'
            Trainer trainer = Trainer(payable(trainers[trainerAddr]));
            // --- FIM DA CORREÇÃO ---

            if (isMatch(Requirements, trainer)) {
                candidates[candidatesCount] = trainerAddr;
                candidatesCount = candidatesCount + 1;
            }
            i = i + 1;
        }
        return candidates;
    }

    function isMatch(DataTypes.JobRequirements memory Requirements, Trainer trainer) internal view returns (bool){
        (int trainerRating, string[] memory trainerTags, DataTypes.Specification memory spec) = trainer.getProfile();

        if (Requirements.minRating > 0 && trainerRating < int(Requirements.minRating)) {
            return false;
        }

        if (Requirements.tags.length > 0) {
            for (uint256 i = 0; i < Requirements.tags.length; i++) {
                if (!containsTag(trainerTags, Requirements.tags[i])) {
                    return false;
                }
            }
        }

        if (bytes(Requirements.description).length > 0) {
            bytes32 requiredDescHash = keccak256(bytes(Requirements.description));
            if (
                requiredDescHash != keccak256(bytes("")) &&
                requiredDescHash != keccak256(bytes(spec.cpu)) &&
                requiredDescHash != keccak256(bytes(spec.processor))
            ) {
                return false;
            }
        }
        return true;
    }

    function containsTag(string[] memory pool, string memory tag) internal pure returns (bool) {
        bytes32 expected = keccak256(bytes(tag));
        for (uint256 i = 0; i < pool.length; i++) {
            if (keccak256(bytes(pool[i])) == expected) {
                return true;
            }
        }
        return false;
    }

    function MakeOffer(
        string memory description,
        bytes32 modelCIDHash,
        bytes32 serverEndpointHash,
        bytes calldata encryptedMetadata,
        uint256 valueByUpdate,
        uint256 numberOfUpdates,
        address trainerCandidate
    ) external {
        require(
            isRequester(msg.sender), "Requester not registered"
        );

        (address trainerWallet, Trainer trainer) = resolveTrainer(trainerCandidate);

        DataTypes.Offer memory offer;
        offer.ID              = nextID();
        offer.description     = description;
        offer.modelCIDHash    = modelCIDHash;
        offer.serverEndpointHash = serverEndpointHash;
        offer.encryptedMetadata = encryptedMetadata;
        offer.valueByUpdate   = valueByUpdate;
        offer.numberOfUpdates = numberOfUpdates;
        offer.offerMaker      = msg.sender;
        offer.trainer         = trainerWallet;

        trainer.newOffer(offer);

        emit OfferMade(offer.ID, msg.sender, trainerWallet);
    }

    function getPendingOffers() external view returns(uint256 [] memory) {
        require(
            isTrainer(msg.sender), "Just registered trainners can check pending offer"
        );
        Trainer trainer = Trainer(payable(trainers[msg.sender]));
        return trainer.getPendingOffers(); // Agora retorna uint256[]
    }

    function AcceptOffer(uint256 offerID) external {
        require(
            isTrainer(msg.sender), "Just registered trainners can accept an offer"
        );

        Trainer trainer = Trainer(payable(trainers[msg.sender])); // Correção de casting

        DataTypes.Offer memory offer = trainer.acceptOffer(offerID);
        if (offer.offerMaker != address(0)) {
            Requester offerMaker = Requester(payable(requesters[offer.offerMaker])); // Correção de casting
            JobContract newContract = new JobContract(offer);

            emit JobContractCreated(address(newContract), offer.ID, offer.offerMaker, offer.trainer);
            offerMaker.newContract(newContract);
            trainer.newContract(newContract);

            jobContracts[address(newContract)] = newContract;
        }
    }

    function signJobContract(address addrContract) public payable {
        require(
            address(jobContracts[addrContract]) != address(0), "Job Contract not found"
            );

        JobContract job    = jobContracts[addrContract];

        bool bIsTrainer    = (msg.sender == job.trainerAddr());
        bool bIsOfferMaker = (msg.sender == job.offerMakerAddr());

        require(
            ((bIsTrainer) || (bIsOfferMaker)), "Just the trainer and the OfferMaker can assign the contract"
        );

        if (bIsOfferMaker) {
            require(
                msg.value == job.totalAmount(), "Should be sent the exactly value to be locked"
            );
            job.deposit{value: msg.value}();
        }

        job.sign(msg.sender);
    }

    function releaseJobPayment(address addrContract, address payable recipient) external {
        require(isJob(addrContract), "Job Contract not found");
        JobContract job = jobContracts[addrContract];
        require(
            msg.sender == job.offerMakerAddr() || msg.sender == job.trainerAddr(),
            "Unauthorized release"
        );
        job.releaseToTrainer(recipient);
    }

    function publishGlobalModel(address addrContract, bytes32 cidHash, bytes calldata encryptedCid) external {
        require(isJob(addrContract), "Job Contract not found");
        JobContract job = jobContracts[addrContract];
        require(
            msg.sender == job.offerMakerAddr() || msg.sender == job.trainerAddr(),
            "Unauthorized publisher"
        );
        job.publishGlobalModel(cidHash, encryptedCid);
    }

    function getOfferDetails(uint256 offerID) external view returns (DataTypes.Offer memory) {
        require(
            isTrainer(msg.sender), "Trainer must be registered"
        );
        Trainer trainer = Trainer(payable(trainers[msg.sender]));
        return trainer.getOfferDetails(offerID);
    }

    function recordClientUpdate(address addrContract, bytes32 cidHash, bytes calldata encryptedCid) external {
        require(isJob(addrContract), "Job Contract not found");
        JobContract job = jobContracts[addrContract];
        require(
            msg.sender == job.trainerAddr() || msg.sender == job.offerMakerAddr(),
            "Unauthorized reporter"
        );
        job.recordClientUpdate(cidHash, encryptedCid);
    }

    function isTrainer(address trainer) internal view returns (bool){
        return (trainers[trainer] != address(0));
    }

    function resolveTrainer(address candidate) internal view returns (address wallet, Trainer trainer) {
        address trainerContractAddr = trainers[candidate];
        if (trainerContractAddr != address(0)) {
            return (candidate, Trainer(payable(trainerContractAddr)));
        }

        if (!Address.isContract(candidate)) {
            revert("Trainer not found");
        }

        Trainer trainerContract = Trainer(payable(candidate));
        address owner = trainerContract.owner();
        address mappedContract = trainers[owner];

        require(mappedContract == address(trainerContract) && owner != address(0), "Trainer not found");

        return (owner, trainerContract);
    }

    function isMember(address account) internal view returns (bool) {
        return isTrainer(account) || isRequester(account);
    }

    function isJob(address addr) public view returns (bool) {
    return address(jobContracts[addr]) != address(0);
    }

    function isRequester(address requester) internal view returns (bool){
        return (requesters[requester] != address(0));
    }
}