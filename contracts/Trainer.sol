// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
import "./DataTypes.sol";
import "./JobContract.sol";

contract Trainer {
    string   public      description;   // Descrição texto livre do treinador
    string[] public      tags;          // Lista de tags do treinador.
    uint256  public      rating;
    DataTypes.Evaluation[]  public  evaluations;    // List of received evaluation
    DataTypes.Specification public  specification; // Specifications of the trainer.
    string public dataPreviewCID;
    uint256 public pricePerUpdate;
   
    uint256[] internal pendingOffersIDs;      
    mapping(uint256 => DataTypes.Offer) private pendingOffers; //<offerID, Offer> Ofertas de trabalho que o treinador tem.

    address[] internal jobsAddress;
    mapping(address => JobContract) private jobContracts;       // Trabalhos atuais do treinador
    
    address public owner;                           // Endereço da carteira do Trainer
    address public DAO;                      // DAO é o endereço do contrato que faz o gerenciamento da DAO
    
    uint256 private evaluationCount;
    uint256 private cumulativeScore;

    constructor(address ownerAddress, string memory _description, DataTypes.Specification memory _specification) {
        DAO    = msg.sender;
        owner         = ownerAddress;
        description   = _description;
        specification = _specification;
        rating        = 10; //Todos treinadores começam com nota maxima
    }

    modifier onlyOwner {
      require(msg.sender == owner,  "Only owner");
      _;
    }

    modifier onlyDAO {
      require(msg.sender == DAO, "Only DAO");
      _;
    }

    function setDescription (string memory _description) external onlyOwner {
        description = _description;
    }

    function setTags (string[] memory  _tags) external onlyOwner {
        tags = _tags;
    }

    function setPricePerUpdate(uint256 price) external onlyOwner {
        pricePerUpdate = price;
    }

    function newOffer(DataTypes.Offer memory offer) external onlyDAO {
        insertOffer(offer);
    }

    function newContract(JobContract job) external onlyDAO {
        insertContract(job);
    }

    function acceptOffer(uint256 offerID) external onlyDAO returns(DataTypes.Offer memory) {
        DataTypes.Offer memory offer;

        if(containsOffer(offerID)){
            offer = pendingOffers[offerID];
            deleteOffer(offerID);
        }

        return offer;
    }

    function getPendingOffers() external view onlyDAO returns(DataTypes.Offer [] memory) {

        DataTypes.Offer [] memory listPendingOffers = new DataTypes.Offer[](pendingOffersIDs.length);

        for (uint256 i = 0; i < pendingOffersIDs.length; i++) {
            DataTypes.Offer memory pendingOffer = pendingOffers[pendingOffersIDs[i]];

            listPendingOffers[i] = pendingOffer;            
        }

        return listPendingOffers;
    }

    function containsOffer(uint256 offerID) public view returns (bool){
        return (pendingOffers[offerID].trainer != address(0));
    }

    function getProfile() external view returns (uint256, string[] memory, DataTypes.Specification memory, uint256) {
        return (rating, tags, specification, pricePerUpdate);
    }

    function recordEvaluation(int256 score, string calldata comment) external onlyDAO {
        require(score >= 0 && score <= 10, "Score out of bounds");

        evaluations.push(DataTypes.Evaluation({comment: comment, rating: score}));
        cumulativeScore += uint256(int256(score));
        evaluationCount += 1;

        rating = cumulativeScore / evaluationCount;
    }

    //FUNÇÕES AUXILIARES
    function insertOffer(DataTypes.Offer memory offer) internal {
        pendingOffers[offer.ID] = offer;
        pendingOffersIDs.push(offer.ID);
    }

    function insertContract(JobContract job) internal {
        jobContracts[address(job)] = job;
        jobsAddress.push(address(job));
    }

    function deleteOffer(uint256 offerID) internal {
        uint256 idxOffer = 0;
        bool    bFound   = false;
        //acha o index que a oferta está
        while ((idxOffer < pendingOffersIDs.length) && (!bFound)){
            if (pendingOffersIDs[idxOffer] == offerID) {
                bFound = true;
                break;
            }
            idxOffer++;
        }

        //Deleta
        if (bFound) {
            //Deleta a oferta da lista de IDs pendentes. Faz isso atribuindo no valor da ultima oferta no lugar da oferta a ser deletada, e então fazendo um pop do ultimo elemento.
            pendingOffersIDs[idxOffer] = pendingOffersIDs[pendingOffersIDs.length-1];
            pendingOffersIDs.pop();


            //Deleta a oferta do mapping
            delete pendingOffers[offerID];
        }
    }
}
